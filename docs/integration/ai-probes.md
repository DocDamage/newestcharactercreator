# Local AI connectivity probes (read-only)

The UCC core can safely check whether already-installed ComfyUI and Stable Diffusion WebUI services respond on **explicit loopback HTTP ports**. This is a lightweight foundation for future selected-provider workflows, not an image generation integration.

## Command

From repo root:

```powershell
$env:PYTHONPATH = "src"
py -3 -m ucc probe-ai --comfyui "http://127.0.0.1:8188" --webui "http://127.0.0.1:7860"
```

You can change the port. The first version accepts only `http://127.0.0.1`, `http://localhost` or `http://[::1]` with an explicit port. Credentials, custom paths, nonlocal addresses and redirects are rejected by design. No server is installed or launched.

- ComfyUI probe requests `GET /system_stats` and reports only the API version and availability.
- Stable Diffusion WebUI probe requests `GET /sdapi/v1/sd-models`, reports only the count of models and **never prints checkpoint names or paths**.
- Errors are returned as `reachable: false` with a diagnostic category, not misleading zero models or a fabricated online state.
- **No `POST` requests** are made: prompts, reference images, checkpoints and other user data are not uploaded or modified.
- Remote/cloud AI will require a separate explicit selection, consent and credential/configuration contract. Do not add a permissive URL override to these functions.

## Verification

Tests run against an in-process fake local HTTP service. These tests validate request behavior and privacy constraints. They do **not** establish availability of the user's actual ComfyUI/WebUI installations or verify workflow compatibility. Real API capability discovery and graph validation will follow the MPFB-based first character milestone.
