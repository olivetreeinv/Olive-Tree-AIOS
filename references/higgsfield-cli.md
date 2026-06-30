# Higgsfield CLI Reference — Olive Tree Investments

CLI for AI-generated images and video for Instagram content. Used by the `/social-media` skill for Reels and product/property visuals.

**Aliases:** `higgsfield`, `higgs`, `hf`
**Version:** 0.1.40 | **Installed:** global (`npm install -g @higgsfield/cli`)

---

## Auth

```bash
# First-time login (browser-based device flow)
hf auth login

# Check current token
hf auth token

# Check account balance + plan
hf account status

# View recent credit usage
hf account transactions --size 20
```

---

## Core Workflow: Instagram Content

### Step 1 — Upload source image or video

```bash
# Upload a local file (returns an upload UUID)
hf upload create ./property-photo.jpg

# List previously uploaded assets
hf upload list --image
hf upload list --video --size 20
```

### Step 2 — Estimate cost before generating

```bash
# Cost check for any model/job
hf generate cost nano_banana_2 --prompt "cinematic aerial view of apartment complex"
hf generate cost <video_model> --prompt "slow pan across apartment building exterior"
```

### Step 3 — Generate

```bash
# Image — product/property shot (most common for IG carousels)
hf generate create nano_banana_2 \
  --prompt "cinematic exterior shot of apartment complex, golden hour, Atlanta skyline" \
  --image ./property.jpg \
  --wait

# Product photoshoot (brand-enhanced, good for deal graphics)
hf product-photoshoot create \
  --mode lifestyle_scene \
  --prompt "multifamily apartment building for Instagram post" \
  --image ./property.jpg \
  --count 3 \
  --wait

# Video / Reel generation
hf generate create <video_model> \
  --prompt "cinematic slow push-in on Atlanta apartment building, professional real estate" \
  --image <upload_uuid> \
  --wait --wait-timeout 20m --wait-interval 10s
```

### Step 4 — Check job status

```bash
# Get job result by ID
hf generate get <job_id>

# Wait for a job to finish (if not using --wait inline)
hf generate wait <job_id>

# List recent jobs
hf generate list
```

---

## Marketing Studio (DTC Ads)

Use for branded ad-style images — investor-facing graphics, deal teasers, quote cards.

```bash
# List brand kits (pull ID for use in DTC ads)
hf marketing-studio brand-kits list

# Create brand kit from Olive Tree website
hf marketing-studio brand-kits fetch --url https://olivetreeinv.io --wait

# List ad format presets
hf marketing-studio ad-formats list

# Generate a DTC ad image
hf marketing-studio dtc-ads generate \
  --prompt "apartment investing opportunity in Atlanta" \
  --format-id <format_uuid> \
  --brand-kit-id <brand_kit_uuid>

# List available hooks (text overlays, call-outs)
hf marketing-studio hooks list

# List saved products (property/deal images)
hf marketing-studio products list

# Create a product from upload
hf marketing-studio products create \
  --title "Deal Property Name" \
  --image <upload_uuid>
```

---

## Soul ID (Character References)

For creating consistent brand personas or avatars in video content.

```bash
# Create a Soul reference (5 images required)
hf soul-id create --name "Brian" --soul-2 \
  --image <id1> --image <id2> --image <id3> --image <id4> --image <id5>

# Check training status
hf soul-id wait <soul_id>

# List all Soul references
hf soul-id list
```

---

## List Available Models

```bash
# All models
hf model list

# Image models only
hf model list --image

# Video models only
hf model list --video

# JSON output for scripting
hf model list --video --json
```

---

## Output Flags

```bash
--json       # Raw JSON — use for scripting / piping to jq
--no-color   # Disable color output (useful in CI or logs)
--wait       # Block until job finishes, print result URL(s)
--wait-timeout 20m   # Max wait time (default 10m for images)
--wait-interval 10s  # Poll interval (default 3s)
```

---

## Olive Tree Use Cases

| Content Type | Command Path | Notes |
|---|---|---|
| IG Carousel hero image | `generate create nano_banana_2` | Upload property photo first |
| Property lifestyle shot | `product-photoshoot create --mode lifestyle_scene` | Backend prompt enhancement |
| IG Reel / video | `generate create <video_model>` | Check `model list --video` for current models |
| Investor-facing ad graphic | `marketing-studio dtc-ads generate` | Requires brand kit ID |
| Quote card / text graphic | `marketing-studio dtc-ads generate` | Use headline ad format |
| Consistent brand persona | `soul-id create` | 5 reference images needed |

---

## Common Patterns for `/social-media` Skill

### Property photo → carousel hero image

```bash
UPLOAD=$(hf upload create ./property.jpg --json | jq -r '.id')
hf generate create nano_banana_2 \
  --prompt "cinematic real estate photo, golden hour, [city], professional photography" \
  --image $UPLOAD \
  --wait --json | jq -r '.outputs[].url'
```

### Generate 3 Reel thumbnail options

```bash
hf product-photoshoot create \
  --mode lifestyle_scene \
  --prompt "multifamily apartment investment opportunity in [city]" \
  --image $UPLOAD \
  --count 3 \
  --wait
```

### Check cost before any generation

```bash
hf generate cost nano_banana_2 --prompt "your prompt here"
```

---

## Notes

- Always run `hf generate cost` before generating — credits are real money. Flag cost to Brian before batch runs.
- `--wait` is preferred for single jobs. For batch (3+ jobs), submit without `--wait`, collect job IDs, then `hf generate wait <id>` in parallel.
- JSON output + `jq` is the fastest path for scripting; use `--json` any time output feeds another command.
- Upload IDs are reusable — no need to re-upload the same asset for variant runs.
- Soul ID training takes several minutes; always use `soul-id wait` before referencing a new Soul in generation.
- Run `hf account status` at the start of any batch session to confirm credit balance.
