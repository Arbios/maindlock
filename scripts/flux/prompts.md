# FLUX portraits — style + character prompts

Goal: 4 cohesive character portraits for the Mindlock rooms, plus a **style LoRA** (Well-Tuned
+ BFL lane). Trained on Modal (FLUX.2). Trigger word: **`mndlck`**.

## Shared style anchor (every prompt prepends this)
> `mndlck style, oil-painting character portrait, head-and-shoulders, chiaroscuro candle-light,
> desaturated muted palette, 19th-century asylum, weathered painterly brushwork, dark vignette
> background, somber, cinematic`

## The four characters (from their biographies)

**The Warden** — *holds the key; gruff, proud, weary, carries old shame*
> `an old weary prison warden, grey stubble, heavy-lidded tired eyes, deep-lined face, worn
> dark uniform, a tarnished iron key ring at his belt, guarded proud expression, a flicker of
> shame behind the eyes`

**Lena** — *night nurse, 20 years, kind but guarded, watchful*
> `a tired middle-aged night nurse, soft watchful eyes, faded grey nurse's uniform, hair pinned
> back under a worn cap, gentle but weary, a brass lantern glowing beside her`

**Doctor Aldous** — *cold, precise, buried guilt, defensive*
> `a cold precise doctor in his fifties, thin wire-rim glasses, starched high collar, severe
> clipped features, clutching a leather records ledger, a flicker of buried guilt in his stare`

**Sam** — *fragile former patient, paranoid, perceptive, fragmented*
> `a fragile gaunt young former patient, wary darting eyes, threadbare hospital gown, unkempt
> hair, hyper-alert, huddled half in shadow`

## Pipeline (on Modal, once authed)
1. **Dataset** — generate ~16–20 style-reference images with base FLUX.2 (varied subjects, this
   aesthetic), caption each with the `mndlck` trigger.
2. **Train** — ai-toolkit FLUX.2 LoRA on the set (BASE checkpoint), ~1h on A100/H100.
3. **Portraits** — render the 4 characters above with base FLUX.2 (DISTILLED) + the LoRA.
4. **Publish** — push the LoRA to HF → Well-Tuned badge + BFL lane.

Notes: characters are invented (no reference photos), so this is a **style** LoRA, not a
likeness LoRA. Per-character identity comes from the prompts; the LoRA gives cohesion + the badge.
