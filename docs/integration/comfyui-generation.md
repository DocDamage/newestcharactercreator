# Local ComfyUI text-to-image workflow — explicit, private operation

UCC now contains an **optional localhost-only** text-to-image job adapter using built-in ComfyUI default nodes. It is not a cloud service, an image-to-3D model, a retargeter, or a rigged character generator. Its output can serve as a **concept/reference image** for future, reviewed body-part construction. The adapter does not install or launch ComfyUI, download checkpoints, execute arbitrary custom workflows, upload Fab assets, or replace your existing models.

This adapter follows ComfyUI's official default API-format graph and "/prompt" → "/history" → "/view" pattern. Relevant references: [ComfyUI basic API example](https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/basic_api_example.py), [ComfyUI WebSocket example](https://github.com/Comfy-Org/ComfyUI/blob/master/script_examples/websockets_api_example.py).

## Preparation

Start your own installed ComfyUI normally on localhost, with a user-permitted checkpoint installed. Use `py -3 -m ucc probe-ai` to confirm the API is reachable. The adapter requires built-in node classes: `CheckpointLoaderSimple`, `CLIPTextEncode`, `EmptyLatentImage`, `KSampler`, `VAEDecode`, `SaveImage`. It verifies the **exact checkpoint** is listed by `GET /models/checkpoints` before any generation request. If the API or nodes differ, it fails and reports why instead of substituting untested custom nodes.

## CLI usage (PowerShell)

```powershell
$env:PYTHONPATH = 'src'
py -3 -m ucc.ai generate --checkpoint 'YOUR_INSTALLED_CHECKPOINT.safetensors' --prompt 'A neutral original fantasy character concept, full body A-pose, front view, isolated background' --width 512 --height 512 --steps 20 --seed 1729 --confirm-local-execution
```

Replace the sample checkpoint name with **exactly one checkpoint already listed by your local ComfyUI**. Omitting `--confirm-local-execution` refuses to submit the job and does not contact the server. The command returns a ComfyUI `prompt_id` and a digest of the submitted workflow, but it does **not** claim a PNG already exists.

Once the job has completed in ComfyUI, get the image(s) without leaving the local computer:

```powershell
py -3 -m ucc.ai fetch 'YOUR-RETURNED-PROMPT-UUID' --output-dir 'C:\UCC\ConceptImages'
```

The second command returns `PENDING` when there is no finished history. When history contains PNG images from our expected `SaveImage` node, it downloads them using bounded loopback requests, verifies image framing/CRC/dimensions, stages them, and publishes them under deterministic names without overwriting prior outputs. Files are **local and unreviewed** until you inspect quality, source-model permissions, and suitability for your project.

## Resource safety and privacy

- The adapter accepts `http://127.0.0.1:<port>`, `http://localhost:<port>`, or IPv6 loopback only. Remote hosts, embedded credentials, proxies, redirects, paths and query fragments are rejected.
- The only generation workflow UCC builds has seven audited built-in node types with fixed references. It permits text prompts only, no image upload, node installation, custom code, external API nodes, or model switching outside a single checkpoint loader.
- GPU-heavy work is not queued concurrently by UCC automatically. Users should avoid launching this job while another ComfyUI image task or heavy Blender GPU render is active on the RTX 3060 12 GB. There is no claim about memory usage of every checkpoint; model compatibility and licenses vary.
- The job's precise model identity is verified locally but not included in the returned CLI summary; prompts are not uploaded to GitHub or cloud services.
- The application does not call ComfyUI's global `/interrupt` because it could cancel an unrelated job. Cancel in ComfyUI itself if needed.
- A PNG does not prove that an editable 3D mesh or separate rigged body parts exist. Those remain contingent on verified Blender 5.3 and MPFB compatibility, real topology work, and quality review.

## Verification

Automated tests use an in-process fake localhost HTTP server, not the user's live ComfyUI. They confirm no submission without explicit approval, required model/node checks, safe fixed workflow wiring, UUID handling, pending responses, hard response-size limits, refusal of traversal filenames, rejection of invalid PNG, and failure rollback. **No actual model inference was run** during CI; the real checkpoint/runtime is a separate manual integration test and should remain `NOT_TESTED` until observed.
