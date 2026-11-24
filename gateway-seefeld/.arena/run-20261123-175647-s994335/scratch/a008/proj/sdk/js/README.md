# @jerumed-nexus/gateway-sdk

TypeScript SDK for the JerumedNexus Gateway REST API.

## Install

```bash
npm install @jerumed-nexus/gateway-sdk
```

## Use

```typescript
import { GatewayClient } from '@jerumed-nexus/gateway-sdk';

const c = new GatewayClient({
  baseUrl: 'https://gateway.mypraxis.example',
});

await c.login('admin', 'password');
const s = await c.status();
console.log(`${s.results_today} messages today, ${s.errors_today} errors`);

// Add a new device from code
await c.createDevice({
  id:           'sysmex-xn-330',
  transport:    'tcp',
  type:         'sysmex_astm',
  listen_port:  5013,
  display_name: 'Sysmex XN-330',
  vendor:       'Sysmex',
  model:        'XN-330',
  enabled:      false,
});
```

## Publish to npm

```bash
cd sdk/js
npm install
npm run build
npm publish --access public
```
