# Remote browser access

Run the native games on a dedicated macOS host. Participant browsers on Windows, macOS or Linux connect to that host's study service through your own HTTPS reverse proxy. Configure the exact public origin and preserve Host; do not expose arbitrary native control or private run directories.

```sh
uv run screenplay-human serve --data runs/my-study --port 8790 --public-origin https://study.example.org
```

`study.example.org` is a placeholder, not a live deployment. Keep the service bound to loopback behind your proxy. Keep admin credentials separate from invitation links. Back up the study directory and wait until no attempt is active or paused before restarting it.

Optional Cloudflare gateway source is provided in `deploy/cloudflare/`. Provision your own account, domain, service bindings and tunnel credentials; none are supplied. Cloudflare resource operations use the cf CLI unless a Wrangler configuration is introduced. Browser clients do not need model API credentials.
