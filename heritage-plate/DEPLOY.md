# Deploying Heritage Plate on Nebius

One container (FastAPI + static UI) on port `8000`, health check at `/api/health`.
The front end and the API share one origin, so CORS needs no setup.

- **Quickest (about 15 min, no Docker on your laptop):** a Nebius VM that builds the app itself with `scripts/deploy_vm.sh`. See below.
- **Path A (about 30 to 45 min):** Nebius **Serverless AI Endpoint** (a container on a CPU VM, managed HTTPS URL).
- **Path B (fallback, about 30 min):** a small Nebius **Compute** CPU VM running Docker with Caddy for automatic HTTPS.
- **Backup:** a `MOCK=1` copy of the app, or the single-file preview from `scripts/build_preview.py`.

> Sources: docs.nebius.com could not be fetched directly from the research environment. The commands below come from Nebius docs search excerpts, Nebius's own GitHub repos (`nebius/skills`, `nebius/serverless-ai-cookbook`) and one public hackathon repo that deploys a FastAPI endpoint. Lines marked **[verify]** were not confirmed word for word. Before you run anything, check with `nebius ai endpoint create --help` and `--dry-run`.

---

## Quickest: one script on a Nebius VM

1. **Create the VM** in the Nebius console: Compute → Virtual machines → Create.
   - Platform: a CPU platform (e.g. `cpu-d3`), preset `2vcpu-8gb` or `4vcpu-16gb`.
   - Boot image: Ubuntu 22.04 or 24.04, disk 20–30 GB.
   - Network: tick **Public IP**.
   - Access: add your SSH public key (`cat ~/.ssh/id_ed25519.pub`) and a username, e.g. `demo`.
2. **Open ports 80 and 443** to the internet if your security group blocks them (Caddy needs 80 to get the HTTPS certificate).
3. **SSH in and run one command** (it asks for your Nebius key with hidden input; the LangSmith key is optional):
   ```bash
   ssh demo@<VM public IP>
   curl -fsSL https://raw.githubusercontent.com/ishtrain07/ishtrain07/claude/stoic-wozniak-8ie5mb/heritage-plate/scripts/deploy_vm.sh | sudo bash
   ```
   It prints `"mode":"live"` and the URL, `https://<ip-with-dashes>.sslip.io`.
4. **Redeploy after any code change or rename:** run the same command again. The URL stays the same. To change keys: `sudo rm /opt/heritage-plate/hp.env` and rerun.
5. **Stop paying:** stop the VM in the console when you're not testing.

---

## 0. Prerequisites (Paths A and B)

```bash
nebius version                      # the nebius/skills guide asks for CLI >= 0.12.277
nebius profile list                 # logged in?
export PROJECT_ID=$(nebius config get parent-id)
export REGION=eu-north1             # use your project's region
export SUBNET_ID=$(nebius vpc subnet list --parent-id "$PROJECT_ID" --format json | jq -r '.items[0].metadata.id')
```

Build an x86 image (required if you build on Apple Silicon):

```bash
cd heritage-plate
docker build --platform linux/amd64 -t heritage-plate:latest .
docker run --rm -p 8000:8000 -e MOCK=1 heritage-plate:latest   # smoke test: http://localhost:8000/api/health
```

---

## Path A: Serverless AI Endpoint (fastest)

How it works (from the docs):
- An endpoint is a container on a Compute VM. It gets a **managed HTTPS URL** for each HTTP `--container-port`, so you don't need a domain or certificate.
- **Billing:** Serverless AI uses Compute VM and disk prices. You pay from create to delete, **including idle time**. A stopped endpoint costs nothing. **There is no scale to zero** to rely on. Some docs mention autoscaling, but the Nebius blog calls it a roadmap item. Stop or delete the endpoint after the demo.
- **Rough cost:** `cpu-d3` `4vcpu-16gb` is about **$0.10 to $0.18 per hour** (two different figures found, neither from the official price list; check nebius.com/prices). That is a few dollars per day at most.
- **No `endpoint update`:** to change the image, env or preset you create a new endpoint and delete the old one, and **the URL changes**. Lock the URL before you record.
- **Auth:** don't pass `--auth token`. Token auth requires a Bearer header on every path, which blocks the browser UI. Leaving `--auth` out means no auth. The app has its own per-client `RATE_LIMIT` to protect credits.

### A1. Push the image to Nebius Container Registry

```bash
export REGISTRY_ID=$(nebius registry create --name heritage-plate --parent-id "$PROJECT_ID" --format json | jq -r '.metadata.id')
export REGISTRY_FQDN=cr.$REGION.nebius.cloud            # or: nebius registry get "$REGISTRY_ID" -> .status.registry_fqdn
export IMAGE="$REGISTRY_FQDN/${REGISTRY_ID#registry-}/heritage-plate:v1"   # path = registry ID without the "registry-" prefix

nebius iam get-access-token | docker login "$REGISTRY_FQDN" --username iam --password-stdin
docker tag heritage-plate:latest "$IMAGE"
docker push "$IMAGE"
```

### A2. Put the secrets in MysteryBox (console name: SecretStash)

Each `--env-secret KEY=<secret>` reads the payload entry whose key matches `KEY`, so the payload keys must be named exactly like the env vars.

```bash
nebius mysterybox secret create --name heritage-plate-secrets --parent-id "$PROJECT_ID" \
  --secret-version-payload '[{"key":"NEBIUS_API_KEY","string_value":"<real key>"},{"key":"LANGSMITH_API_KEY","string_value":"<langsmith key>"}]'
```
**[verify]** the exact shape of the `--secret-version-payload` JSON with `nebius mysterybox secret create --help`. If it gives you trouble, use the console instead (SecretStash → Create secret). Avoid `--env NEBIUS_API_KEY=...`: plain env values can show up in `endpoint get` output.

### A3. Create the endpoint

```bash
nebius ai endpoint create \
  --name heritage-plate \
  --parent-id "$PROJECT_ID" \
  --image "$IMAGE" \
  --registry-username iam \
  --registry-password "$(nebius iam get-access-token)" \
  --platform cpu-d3 \
  --preset 4vcpu-16gb \
  --container-port 8000 \
  --subnet-id "$SUBNET_ID" \
  --env RATE_LIMIT=100 \
  --env LANGSMITH_TRACING=true \
  --env LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com \
  --env LANGSMITH_PROJECT=heritage-plate \
  --env-secret NEBIUS_API_KEY=heritage-plate-secrets \
  --env-secret LANGSMITH_API_KEY=heritage-plate-secrets \
  --dry-run          # remove this flag once the plan looks right
```

Notes:
- `cpu-d3` / `4vcpu-16gb` matches the official nginx quickstart. Check what your region offers with `nebius compute platform list`. eu-west1 only has `cpu-d3`. A smaller preset such as `2vcpu-8gb` may also work **[verify]**.
- `--public` is optional. It adds a public IP, but the HTTPS URL works without it.
- **[verify]** The registry password is a short-lived IAM token. If the endpoint pulls the image again later (restart), the pull may fail. Simple workaround: push the image to a public registry (GHCR or Docker Hub; the image contains no secrets) and leave out the `--registry-*` flags.
- The CLI can print a local error even when the create succeeded. Check with `nebius ai endpoint get-by-name --name heritage-plate` before you retry.

### A4. Get the URL and check it

```bash
nebius ai endpoint get-by-name --name heritage-plate --parent-id "$PROJECT_ID" --format json \
  | jq '{state: .status.state, urls: .status.public_endpoints}'     # don't print the full output: it can contain secrets
export URL=https://<host from public_endpoints>
curl -sS "$URL/api/health" | jq        # expect "mode": "live"
nebius ai endpoint logs <endpoint_ID>  # if it is not up yet  [verify flags with --help]
```

While the image is still starting you may get `502 failed to connect to local service`. Wait and retry.

### A5. Redeploy, stop, delete

```bash
# Redeploy = push a new tag (v2), run A3 with a new --name, check it, then delete the old endpoint.
nebius ai endpoint stop   <endpoint_ID>     # stops billing; start again with: nebius ai endpoint start <endpoint_ID>
nebius ai endpoint delete <endpoint_ID>
```

### Optional: Serverless Job (counts toward the "Endpoints/Jobs" brief)

Run the live end-to-end check as a one-off Job against the same image. It is billed only while it runs:

```bash
nebius ai job create --name hp-live-check --parent-id "$PROJECT_ID" --image "$IMAGE" \
  --registry-username iam --registry-password "$(nebius iam get-access-token)" \
  --platform cpu-d3 --preset 4vcpu-16gb --subnet-id "$SUBNET_ID" \
  --env HP_LIVE=1 --env-secret NEBIUS_API_KEY=heritage-plate-secrets \
  --container-command python --args "scripts/live_run.py"
```
**[verify]** the image does not include `scripts/` (the Dockerfile copies only `app data static`). Add `COPY scripts scripts` first, and confirm the `job create` flags with `--help`.

---

## Path B: Compute CPU VM + Caddy (fallback)

Use this if Serverless endpoints are unavailable in your region or quota. The VM's public IP plus `sslip.io` gives a hostname that Caddy can get a Let's Encrypt certificate for.

### B1. Create the VM

```bash
cat > cloud-init.yaml <<'EOF'
#cloud-config
users:
  - name: demo
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - <your ~/.ssh/id_ed25519.pub contents>
packages: [docker.io]
runcmd:
  - systemctl enable --now docker
  - usermod -aG docker demo
EOF

nebius compute instance create \
  --name heritage-plate-vm \
  --parent-id "$PROJECT_ID" \
  --resources-platform cpu-d3 \
  --resources-preset 4vcpu-16gb \
  --boot-disk-attach-mode read_write \
  --boot-disk-managed-disk-name heritage-plate-boot \
  --boot-disk-managed-disk-type network_ssd \
  --boot-disk-managed-disk-size-gibibytes 30 \
  --boot-disk-managed-disk-source-image-family-image-family ubuntu24.04-driverless \
  --network-interfaces "[{\"name\":\"eth0\",\"ip_address\":{},\"public_ip_address\":{},\"subnet_id\":\"$SUBNET_ID\"}]" \
  --cloud-init-user-data "$(cat cloud-init.yaml)"
```
**[verify]** `--boot-disk-attach-mode` casing (`read_write` or `READ_WRITE`) and the disk type value. If anything fails, run `nebius compute instance create --interactive`, or use the console (Compute → Create VM, tick "Public IP").

```bash
export VM_IP=$(nebius compute instance get-by-name --name heritage-plate-vm --parent-id "$PROJECT_ID" --format json \
  | jq -r '.status.network_interfaces[0].public_ip_address.address' | cut -d/ -f1)
export HOST="$(echo $VM_IP | tr . -).sslip.io"     # e.g. 1-2-3-4.sslip.io
```

Open ports 80 and 443 if your VPC security group blocks them (the default usually allows them) **[verify]**.

### B2. Run the app + Caddy on the VM

```bash
# from your laptop: copy the image (or pull it from the registry in A1)
docker save heritage-plate:latest | gzip | ssh demo@$VM_IP 'gunzip | docker load'

ssh demo@$VM_IP
cat > hp.env <<'EOF'
NEBIUS_API_KEY=<real key>
RATE_LIMIT=100
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
LANGSMITH_PROJECT=heritage-plate
LANGSMITH_API_KEY=<langsmith key>
EOF
chmod 600 hp.env

docker network create web
docker run -d --name hp --restart unless-stopped --network web --env-file hp.env heritage-plate:latest
# backup: a second container in demo mode (no key)
docker run -d --name hp-mock --restart unless-stopped --network web -e MOCK=1 heritage-plate:latest

docker run -d --name caddy --restart unless-stopped --network web -p 80:80 -p 443:443 \
  -v caddy_data:/data caddy:2 \
  caddy reverse-proxy --from <HOST> --to hp:8000
curl -sS https://<HOST>/api/health
```

To serve the mock backup as well, use a Caddyfile with two sites (`<HOST>` → `hp:8000`, `mock.<HOST>` → `hp-mock:8000`) in place of the one-line `reverse-proxy` command.

Redeploy: `docker load` the new image, then `docker rm -f hp`, then rerun the `docker run ... hp` line. The URL stays the same.
Cost: same Compute price as Path A. Run `nebius compute instance stop` or `delete` afterwards.

---

## Pre-demo checklist

- [ ] `RATE_LIMIT` is set (Dockerfile default 100 per client per 10 min, plus `MAX_CALLS_PER_HOUR=600` across everyone). Raise it if several judges or teammates share one NAT IP. `TRUST_PROXY=1` is already set in the image.
- [ ] `curl $URL/api/health` shows **`"mode": "live"`** and the expected Nemotron model IDs. `"mock"` means `NEBIUS_API_KEY` didn't arrive.
- [ ] Warm-up: in the browser, open one family, run "Make every dish lighter" and then "Plan our week" end to end. Confirm "Under the hood" shows live tiers and latencies.
- [ ] Check it on a phone over mobile data (not office Wi-Fi), with the real public URL.
- [ ] LangSmith project `heritage-plate` receives traces (optional).
- [ ] Backup ready: a `MOCK=1` instance (Path B `hp-mock`, or a second endpoint with `--env MOCK=1` and no secrets), **or** `python scripts/build_preview.py /tmp/hp-preview.html` opened locally. Keep its tab open.
- [ ] URL frozen: no redeploys after recording starts (Path A redeploys change the URL).
- [ ] After the demo: stop or delete the endpoint/VM and rotate the API key if it was ever pasted anywhere.

## Sources

- Serverless AI overview: https://docs.nebius.com/serverless/overview
- Managing endpoints (flags, auth, managed HTTPS URL, env/env-secret): https://docs.nebius.com/serverless/endpoints/manage
- Endpoint quickstart (nginx, `cpu-d3` / `4vcpu-16gb`): https://docs.nebius.com/serverless/quickstart/endpoints
- CLI reference `nebius ai endpoint create`: https://docs.nebius.com/cli/reference/ai/endpoint/create
- Pricing and quotas (Compute pricing applies): https://docs.nebius.com/serverless/pricing-quotas and https://nebius.com/prices
- Jobs: https://docs.nebius.com/serverless/jobs/manage and https://docs.nebius.com/cli/reference/ai/job/create
- Container Registry quickstart: https://docs.nebius.com/container-registry/quickstart
- MysteryBox CLI: https://docs.nebius.com/cli/reference/mysterybox/secret
- Compute VM create: https://docs.nebius.com/compute/virtual-machines/manage and https://docs.nebius.com/cli/reference/compute/instance/create
- Public IPs: https://docs.nebius.com/compute/virtual-machines/network
- Nebius agent skill (no update, public URL field, billing): https://github.com/nebius/skills/blob/main/skills/nebius-serverless-endpoints/SKILL.md
- Nebius cookbook (auth token behavior): https://github.com/nebius/serverless-ai-cookbook/blob/main/templates/endpoint-sana/README.md
- Community FastAPI endpoint deploy (registry login, `--registry-*`, `--auth none` for browser UI): https://github.com/dsadchikov/docs-proc-nebius
- Caddy reverse-proxy command: https://caddyserver.com/docs/command-line#caddy-reverse-proxy
