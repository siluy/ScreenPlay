# Optional Cloudflare gateway

`pages.mjs` forwards through a `STUDY_GATEWAY` service binding. `gateway.mjs` restricts forwarding to a `STUDY_SERVICE` VPC binding for the study host. Provision those bindings and your own tunnel in your own account. The files are examples; this repository is not connected to a deployed service.

Use an exact HTTPS origin, preserve Host and validate your configured client-IP header chain. Keep tunnel tokens outside the repository. Run `node --test deploy/cloudflare/test-gateway.mjs` for routing boundary checks. See `docs/remote-access.md` for host setup.
