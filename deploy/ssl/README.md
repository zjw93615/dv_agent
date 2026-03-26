# SSL Certificates Directory

Place your SSL certificates here:
- `cert.pem` - SSL certificate
- `key.pem` - Private key

## Generate Self-Signed Certificates (for testing)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout key.pem \
    -out cert.pem \
    -subj "/CN=localhost"
```

## For Production

Use Let's Encrypt or another trusted CA:
1. Install certbot
2. Run: `certbot certonly --standalone -d your-domain.com`
3. Copy certificates here

**Note**: Never commit real certificates to git!
