# APT repository setup

Ship signed `.deb` updates to customers so they can just run:

```bash
sudo apt update && sudo apt install --only-upgrade jerumednexus-gateway
```

## Server side (one-time)

### 1. Generate a signing key

```bash
gpg --full-generate-key   # 4096-bit RSA, sign-only, no expiry (or short expiry + rotation)
gpg --list-secret-keys --keyid-format=long
```

Note the long key id (e.g. `A1B2C3D4E5F6A7B8`).

### 2. Install and configure reprepro

```bash
sudo apt install reprepro
sudo mkdir -p /var/www/apt.jerumed-nexus.ch/loc200
cd /var/www/apt.jerumed-nexus.ch/loc200

sudo tee conf/distributions <<EOF
Origin: Jerumed Nexus GmbH
Label: JerumedNexus Gateway
Codename: bookworm
Architectures: all
Components: main
Description: JerumedNexus Gateway apt repository
SignWith: A1B2C3D4E5F6A7B8
EOF
```

### 3. Sign and publish a .deb

```bash
GPG_KEY_ID=A1B2C3D4E5F6A7B8 ./scripts/sign-deb.sh dist/jerumednexus-gateway_1.1.0_all.deb
sudo reprepro -b /var/www/apt.jerumed-nexus.ch/loc200 \
    includedeb bookworm dist/jerumednexus-gateway_1.1.0_all.deb

# Export public key
gpg --armor --export A1B2C3D4E5F6A7B8 \
    | sudo tee /var/www/apt.jerumed-nexus.ch/loc200/jerumednexus-gateway-apt.asc
```

### 4. Serve via any HTTPS front-end (Caddy example)

```
apt.jerumed-nexus.ch {
    root * /var/www/apt.jerumed-nexus.ch
    file_server browse
}
```

## Client side (each Pi)

Add the repo:

```bash
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://apt.jerumed-nexus.ch/loc200/jerumednexus-gateway-apt.asc \
    | sudo tee /etc/apt/keyrings/jerumednexus-gateway-apt.asc > /dev/null

echo "deb [signed-by=/etc/apt/keyrings/jerumednexus-gateway-apt.asc] \
https://apt.jerumed-nexus.ch/loc200 bookworm main" \
    | sudo tee /etc/apt/sources.list.d/jerumednexus-gateway.list

sudo apt update
sudo apt install jerumednexus-gateway
```

## Automation

Include the "Add the repo" block in `scripts/bootstrap.sh` so
`curl … | sudo bash` installs from the repo instead of from a raw `.deb`.
This gives you free `apt update` upgrades on every client Pi.

## Key rotation

1. Generate a new key with a subkey expiry (e.g. 2 years).
2. Publish it alongside the old key for 90 days (`gpg --armor --export` both).
3. Re-sign the current release with the new key.
4. After 90 days remove the old key from the repo and revoke it.
