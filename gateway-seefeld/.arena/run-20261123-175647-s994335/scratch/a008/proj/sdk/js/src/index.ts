/**
 * JerumedNexus Gateway SDK -- TypeScript client.
 *
 * @example
 *   import { GatewayClient } from '@jerumed-nexus/gateway-sdk';
 *   const c = new GatewayClient({ baseUrl: 'https://gateway.example.ch' });
 *   await c.login('admin', 'password');
 *   const status = await c.status();
 *   console.log(status.results_today);
 */

export interface ClientOptions {
  baseUrl: string;
  /** Optional bearer token (if using OIDC/API token instead of session cookie). */
  token?: string;
  /** Custom fetch impl (Node <18 without global fetch, jest mocks, etc.). */
  fetch?: typeof fetch;
}

export interface GatewayStatus {
  running: boolean;
  results_today: number;
  results_total: number;
  errors_today: number;
  uptime_seconds: number;
  queue_size: number;
  queue_maxsize: number;
  service_systemd: string;
  targets: Array<{ name: string; type: string; enabled: boolean }>;
  breakers?: unknown[];
  last_seen?: Record<string, string>;
}

export interface DeviceEntry {
  id: string;
  type: string;
  enabled: boolean;
  display_name?: string;
  vendor?: string;
  model?: string;
  serial_port?: string;
  listen_host?: string;
  listen_port?: number;
}

export interface DLQEntry {
  ts: string;
  control_id: string;
  sample_id: string;
  device: string;
  targets: string[];
  errors: Record<string, string>;
  reason: string;
}

export class GatewayClient {
  private baseUrl: string;
  private token?: string;
  private csrfToken?: string;
  private fetchImpl: typeof fetch;
  private cookieJar: string[] = [];

  constructor(opts: ClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/$/, '');
    this.token   = opts.token;
    this.fetchImpl = opts.fetch ?? fetch;
  }

  private headers(json = true): Record<string, string> {
    const h: Record<string, string> = {};
    if (json) h['Content-Type'] = 'application/json';
    if (this.token) h['Authorization'] = `Bearer ${this.token}`;
    if (this.csrfToken) h['X-CSRF-Token'] = this.csrfToken;
    if (this.cookieJar.length) h['Cookie'] = this.cookieJar.join('; ');
    return h;
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const url = this.baseUrl + path;
    const res = await this.fetchImpl(url, {
      ...init,
      headers: { ...this.headers(init.body !== undefined), ...(init.headers ?? {}) },
    });
    const setCookie = res.headers.get('set-cookie');
    if (setCookie) this.cookieJar.push(setCookie.split(';')[0]);
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`${res.status} ${res.statusText}: ${body}`);
    }
    if (res.headers.get('content-type')?.includes('application/json')) {
      return await res.json() as T;
    }
    return await res.text() as unknown as T;
  }

  async login(username: string, password: string): Promise<void> {
    const body = new URLSearchParams({ username, password }).toString();
    await this.fetchImpl(this.baseUrl + '/login', {
      method: 'POST', body,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      redirect: 'manual',
    }).then(res => {
      const setCookie = res.headers.get('set-cookie');
      if (setCookie) this.cookieJar.push(setCookie.split(';')[0]);
    });
  }

  // ── Status
  status():        Promise<GatewayStatus> { return this.request('/api/status'); }
  publicStatus():  Promise<unknown>       { return this.request('/api/status/public'); }
  metrics():       Promise<string>        { return this.request('/metrics'); }
  logs(n = 80):    Promise<{ lines: string[] }> { return this.request(`/api/logs?n=${n}`); }

  // ── Devices
  listDevices():          Promise<{ devices: DeviceEntry[] }> {
    return this.request('/api/devices');
  }
  getDevice(id: string):  Promise<{ ok: boolean; device: DeviceEntry }> {
    return this.request(`/api/devices/${encodeURIComponent(id)}`);
  }
  createDevice(payload: Partial<DeviceEntry> & { transport: 'usb'|'tcp' }):
      Promise<{ ok: boolean; path?: string; error?: string }> {
    return this.request('/api/devices/create', {
      method: 'POST', body: JSON.stringify(payload),
    });
  }
  enableDevice(id: string, enabled = true):
      Promise<{ ok: boolean; enabled?: boolean }> {
    return this.request(`/api/devices/${encodeURIComponent(id)}/enable`, {
      method: 'POST', body: JSON.stringify({ enabled }),
    });
  }
  archiveDevice(id: string): Promise<{ ok: boolean; archived_to?: string }> {
    return this.request(`/api/devices/${encodeURIComponent(id)}/archive`, {
      method: 'POST',
    });
  }

  // ── Targets
  testTarget(name: string):    Promise<unknown> {
    return this.request(`/api/targets/${encodeURIComponent(name)}/test`, { method: 'POST' });
  }
  previewTarget(name: string): Promise<unknown> {
    return this.request(`/api/targets/${encodeURIComponent(name)}/preview`, { method: 'POST' });
  }

  // ── DLQ
  listDLQ(limit = 100): Promise<{ entries: DLQEntry[] }> {
    return this.request(`/api/dlq?limit=${limit}`);
  }
  getDLQ(controlId: string): Promise<{ ok: boolean; hl7: string }> {
    return this.request(`/api/dlq/${encodeURIComponent(controlId)}`);
  }
  replayDLQ(controlId: string, targets?: string[]): Promise<unknown> {
    return this.request(`/api/dlq/${encodeURIComponent(controlId)}/replay`, {
      method: 'POST',
      body: targets ? JSON.stringify({ targets }) : undefined,
    });
  }

  // ── Users
  listUsers():   Promise<unknown> { return this.request('/api/users'); }
  createUser(name: string, password: string, role: 'viewer'|'operator'|'admin'):
      Promise<unknown> {
    return this.request('/api/users', {
      method: 'POST', body: JSON.stringify({ name, password, role }),
    });
  }

  // ── Trace
  traceDevices():                 Promise<{ devices: string[] }> {
    return this.request('/api/trace');
  }
  traceFrames(device: string, limit = 50): Promise<unknown> {
    return this.request(`/api/trace/${encodeURIComponent(device)}?limit=${limit}`);
  }

  // ── History
  searchHistory(params: {
    q?: string; device?: string; status?: string; since?: string;
    limit?: number; offset?: number;
  } = {}): Promise<unknown> {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined) as any).toString();
    return this.request('/api/history' + (qs ? '?' + qs : ''));
  }

  // ── SLA
  slaJSON(period: string): Promise<unknown> {
    return this.request(`/api/sla/${period}`);
  }
  slaHTML(period: string): Promise<string> {
    return this.request(`/api/sla/${period}?format=html`);
  }
}

export default GatewayClient;
