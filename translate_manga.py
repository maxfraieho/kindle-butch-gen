#!/usr/bin/env python3
import os
import sys
import argparse
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import requests
import cv2

# Import our TextDetector and natsort (installed in PRoot container)
try:
    from comic_text_detector.inference import TextDetector
    from comic_text_detector.utils.textmask import REFINEMASK_INPAINT
    from natsort import natsorted
except ImportError as e:
    print(f"Error: Missing dependency in PRoot environment: {e}")
    print("This script must be run inside the PRoot Ubuntu container where packages are installed.")
    sys.exit(1)

def log(msg):
    print(f"[{Path(__file__).name}] {msg}")

def download_detector_model():
    model_dir = "/data/data/com.termux/files/home/kindle-butch-gen/models/comic_text_detector"
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "detector.pt")
    if not os.path.exists(model_path):
        log("Downloading comic text detector model (PyTorch)...")
        url = "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt"
        import urllib.request
        urllib.request.urlretrieve(url, model_path)
        log("Model downloaded successfully!")
    return model_path

def extract_manga_pages(input_path, temp_dir):
    ext = os.path.splitext(input_path)[1].lower()
    if ext == '.pdf':
        log(f"Extracting PDF pages from {input_path}...")
        subprocess.run(['pdftoppm', '-png', '-r', '150', input_path, os.path.join(temp_dir, 'page')], check=True)
    elif ext in ['.zip', '.cbz', '.epub']:
        log(f"Extracting ZIP/CBZ/EPUB pages from {input_path}...")
        import zipfile
        with zipfile.ZipFile(input_path, 'r') as z:
            for file_info in z.infolist():
                if file_info.is_dir():
                    continue
                filename = file_info.filename.lower()
                if not (filename.endswith('.png') or filename.endswith('.jpg') or filename.endswith('.jpeg') or filename.endswith('.webp')):
                    continue
                basename = os.path.basename(file_info.filename)
                if not basename:
                    continue
                target_path = os.path.join(temp_dir, basename)
                with open(target_path, 'wb') as f_out:
                    f_out.write(z.read(file_info.filename))
    elif ext in ['.cbr', '.cb7']:
        log(f"Extracting RAR/7z pages from {input_path} using 7z...")
        subprocess.run(['7z', 'x', f'-o{temp_dir}', input_path], check=True)
        # Move nested images flat to temp_dir
        for root, dirs, files in os.walk(temp_dir):
            if root == temp_dir:
                continue
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    shutil.move(os.path.join(root, file), os.path.join(temp_dir, file))
    else:
        # If it's a folder, copy images
        if os.path.isdir(input_path):
            log(f"Copying images from directory {input_path}...")
            for file in os.listdir(input_path):
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    shutil.copy(os.path.join(input_path, file), os.path.join(temp_dir, file))
        # If it's a single image file
        elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
            log(f"Copying single image file {input_path}...")
            shutil.copy(input_path, os.path.join(temp_dir, os.path.basename(input_path)))
        else:
            raise ValueError(f"Unsupported input format: {ext}")

def _hard_wrap_word(word, font, max_width):
    """Character-level split for a single word wider than max_width on its
    own - wrap_text() below never breaks mid-word otherwise, so an overlong
    word (common in Ukrainian translations of short EN/JA source words)
    would blow past the box no matter how small the font gets. Every break
    except the final piece gets a trailing hyphen for readability (room for
    it is reserved conservatively during the fill, on all pieces, so a
    hyphenated break can never itself overflow)."""
    if not word:
        return [word]
    bbox = font.getbbox(word)
    if bbox[2] - bbox[0] <= max_width:
        return [word]
    pieces = []
    current = ""
    for ch in word:
        candidate = current + ch
        bbox = font.getbbox(candidate + "-")
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            pieces.append(current)
            current = ch
    if current:
        pieces.append(current)
    return [p + "-" if i < len(pieces) - 1 else p for i, p in enumerate(pieces)]

def wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]
        if width <= max_width or not current_line:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
        # If the word we just placed alone still overflows (it was the
        # sole occupant of current_line and didn't fit), hard-wrap it in
        # place rather than silently exceeding max_width downstream.
        if len(current_line) == 1:
            solo_bbox = font.getbbox(current_line[0])
            if solo_bbox[2] - solo_bbox[0] > max_width:
                pieces = _hard_wrap_word(current_line[0], font, max_width)
                lines.extend(pieces[:-1])
                current_line = [pieces[-1]] if pieces else []
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def fit_text(text, font_path, max_width, max_height, min_size=12, max_size_ratio=0.4):
    # Binary search for optimal font size, clamped to a readable floor and
    # a box-relative ceiling instead of the old fixed [8, 80] range.
    low = min_size
    high = max(min_size, min(80, int(max_height * max_size_ratio)))
    best_size = None
    best_lines = None

    def _measure(size):
        try:
            font = ImageFont.truetype(font_path, size)
        except Exception:
            font = ImageFont.load_default()
        lines = wrap_text(text, font, max_width)
        total_height = 0
        max_line_width = 0
        for line in lines:
            bbox = font.getbbox(line)
            total_height += (bbox[3] - bbox[1]) + 2
            max_line_width = max(max_line_width, bbox[2] - bbox[0])
        return lines, total_height, max_line_width

    while low <= high:
        mid = (low + high) // 2
        lines, total_height, max_line_width = _measure(mid)
        if total_height <= max_height and max_line_width <= max_width:
            best_size = mid
            best_lines = lines
            low = mid + 1
        else:
            high = mid - 1

    if best_size is not None:
        return best_size, best_lines

    # No size in [min_size, ceiling] satisfies both constraints - the old
    # code returned the ENTIRE text as one unwrapped line at size 8, which
    # is guaranteed to overflow far worse than a wrapped result at the
    # floor size. Return the floor-size wrapped lines instead: still
    # overflowing (flagged by post_render_check downstream), but readable
    # and box-relative rather than a single giant line.
    fallback_lines, _, _ = _measure(min_size)
    return min_size, fallback_lines

def draw_text_centered(draw, lines, font_path, size, box):
    x1, y1, x2, y2 = box
    box_w = x2 - x1
    box_h = y2 - y1
    
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception:
        font = ImageFont.load_default()
        
    line_heights = []
    total_height = 0
    for line in lines:
        bbox = font.getbbox(line)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_height += h + 2
        
    y_offset = y1 + (box_h - total_height) // 2
    
    for line, h in zip(lines, line_heights):
        bbox = font.getbbox(line)
        w = bbox[2] - bbox[0]
        x_offset = x1 + (box_w - w) // 2
        # Render text with white border outline for visibility
        draw.text((x_offset, y_offset), line, font=font, fill="black", stroke_width=2, stroke_fill="white")
        y_offset += h + 2

def _iou(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

class _MergedBlock:
    """Minimal duck-typed stand-in for comic_text_detector's TextBlock,
    carrying only the union bbox after Stage A dedup - the rest of the
    pipeline (OCR crop, typeset box) only ever reads .xyxy off a block."""
    def __init__(self, xyxy):
        self.xyxy = xyxy

def dedupe_blocks(blk_list, iou_threshold=0.3):
    """Stage A: merge overlapping/duplicate detector blocks - a known
    imperfect-grouping failure mode for large/oval bubbles even after the
    detector's own internal NMS - before OCR, so one physical bubble never
    gets OCR'd/translated/typeset twice (the "double text" defect).
    Union-find so transitively-overlapping chains merge into one group,
    not just directly-overlapping pairs."""
    n = len(blk_list)
    if n <= 1:
        return list(blk_list)
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    for i in range(n):
        for j in range(i + 1, n):
            if _iou(blk_list[i].xyxy, blk_list[j].xyxy) > iou_threshold:
                union(i, j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    merged = []
    for indices in groups.values():
        if len(indices) == 1:
            merged.append(blk_list[indices[0]])
        else:
            xs1 = [blk_list[i].xyxy[0] for i in indices]
            ys1 = [blk_list[i].xyxy[1] for i in indices]
            xs2 = [blk_list[i].xyxy[2] for i in indices]
            ys2 = [blk_list[i].xyxy[3] for i in indices]
            merged.append(_MergedBlock([min(xs1), min(ys1), max(xs2), max(ys2)]))
    return merged

def robust_inpaint(img, mask_refined, blk_list, radius=9):
    """Stage B: TELEA inpaint at a larger radius (was 3px - too thin for
    bold/large source fonts, leaving a visible "ghost" of the original
    text under the new one) plus a per-block solid-fill pass on top,
    where the surrounding background is flat enough to estimate safely
    (typical of manga's solid-color bubble fills)."""
    inpainted = cv2.inpaint(img, mask_refined, radius, cv2.INPAINT_TELEA)
    h_img, w_img = img.shape[:2]
    ring = 6

    for blk in blk_list:
        x1, y1, x2, y2 = blk.xyxy
        bx1, by1 = max(0, x1 - ring), max(0, y1 - ring)
        bx2, by2 = min(w_img, x2 + ring), min(h_img, y2 + ring)
        if bx2 <= bx1 or by2 <= by1:
            continue

        region_mask = mask_refined[by1:by2, bx1:bx2]
        if region_mask.size == 0 or not region_mask.any():
            continue

        # Sample the border ring OUTSIDE the mask for a background color
        # estimate - the mask itself covers where the old text glyphs
        # were, so pixels just outside it are the bubble's fill color.
        border = np.zeros_like(region_mask, dtype=bool)
        border[:ring, :] = True
        border[-ring:, :] = True
        border[:, :ring] = True
        border[:, -ring:] = True
        border &= (region_mask == 0)
        sample_pixels = inpainted[by1:by2, bx1:bx2][border]
        if sample_pixels.shape[0] < 10:
            continue  # not enough clean background sampled - trust TELEA alone

        std = float(np.std(sample_pixels, axis=0).mean())
        if std > 18:
            continue  # background too noisy/textured to safely flat-fill

        bg_color = np.median(sample_pixels, axis=0)
        fill_mask = region_mask.astype(bool)
        inpainted[by1:by2, bx1:bx2][fill_mask] = bg_color

    return inpainted

def get_bubble_box(blk, mask_refined, img_shape, padding_ratio=0.15):
    """Stage C: derive the typeset box from the connected mask region(s)
    the detector/inpaint actually covered for this block, instead of the
    OCR-tight blk.xyxy - the tight bbox is why typeset text overflows
    (translated text needs the bubble's real interior, not just the
    original glyphs' bounding box) or looks disproportionate.

    Multi-line/multi-word text is usually NOT one connected mask blob -
    gaps between lines and letters break 8-connectivity, so a single block
    can correspond to several disconnected components. Picking "the
    component under the block's geometric center" (an earlier version of
    this function) is fragile: the center often lands in a gap between
    lines, landing on background or an unrelated nearby component instead.
    Union the bounding rects of every component that actually overlaps
    the original OCR bbox instead - correctly reconstructs the full
    multi-line extent."""
    h_img, w_img = img_shape[:2]
    x1, y1, x2, y2 = blk.xyxy

    def _padded_bbox_fallback():
        bw, bh = x2 - x1, y2 - y1
        pad_x, pad_y = int(bw * padding_ratio), int(bh * padding_ratio)
        return (int(max(0, x1 - pad_x)), int(max(0, y1 - pad_y)), int(min(w_img, x2 + pad_x)), int(min(h_img, y2 + pad_y)))

    # Small search margin - just enough to recover component edges a
    # too-tight OCR bbox might have clipped, not a scan for "anything
    # nearby" (that's what caused the center-pixel approach to grab
    # unrelated content).
    search_pad = int(max(x2 - x1, y2 - y1) * 0.15) + 2
    sx1, sy1 = max(0, x1 - search_pad), max(0, y1 - search_pad)
    sx2, sy2 = min(w_img, x2 + search_pad), min(h_img, y2 + search_pad)
    region = mask_refined[sy1:sy2, sx1:sx2]
    if region.size == 0 or not region.any():
        return _padded_bbox_fallback()

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((region > 0).astype(np.uint8), connectivity=8)
    if num_labels <= 1:
        return _padded_bbox_fallback()

    orig_x1, orig_y1 = x1 - sx1, y1 - sy1
    orig_x2, orig_y2 = x2 - sx1, y2 - sy1
    union = None
    for label in range(1, num_labels):
        lx = stats[label, cv2.CC_STAT_LEFT]
        ly = stats[label, cv2.CC_STAT_TOP]
        lw = stats[label, cv2.CC_STAT_WIDTH]
        lh = stats[label, cv2.CC_STAT_HEIGHT]
        # Overlap test against the ORIGINAL detection bbox (in this
        # region's local coordinates) - only union components genuinely
        # tied to this block's text, not just anything in the margin.
        ox1, oy1 = max(lx, orig_x1), max(ly, orig_y1)
        ox2, oy2 = min(lx + lw, orig_x2), min(ly + lh, orig_y2)
        if ox2 <= ox1 or oy2 <= oy1:
            continue
        comp = (lx, ly, lx + lw, ly + lh)
        union = comp if union is None else (
            min(union[0], comp[0]), min(union[1], comp[1]),
            max(union[2], comp[2]), max(union[3], comp[3])
        )

    if union is None:
        return _padded_bbox_fallback()

    bx1, by1, bx2, by2 = sx1 + union[0], sy1 + union[1], sx1 + union[2], sy1 + union[3]
    pad_x, pad_y = int((bx2 - bx1) * padding_ratio), int((by2 - by1) * padding_ratio)
    # bx1..by2 can be numpy.int32 (from cv2.connectedComponentsWithStats's
    # `stats` array) rather than plain Python int - cast explicitly so
    # this box is safe to json.dump() (bubbles_meta.json needs it to be),
    # not just safe to pass to cv2/PIL calls (which don't care).
    return (int(max(0, bx1 - pad_x)), int(max(0, by1 - pad_y)), int(min(w_img, bx2 + pad_x)), int(min(h_img, by2 + pad_y)))

def post_render_check(flags, page_name, block_index, chosen_size, wrapped_lines, box, font_path, min_size):
    """Stage E: after typeset, flag anything that still looks wrong so it
    surfaces for review instead of shipping silently. Appends to `flags`
    (a list the caller accumulates per-book and writes to
    quality_flags.json at the end) - does not raise or block the pipeline."""
    x1, y1, x2, y2 = box
    box_w = max(1, x2 - x1)
    try:
        font = ImageFont.truetype(font_path, chosen_size)
    except Exception:
        font = ImageFont.load_default()
    max_line_width = 0
    for line in wrapped_lines:
        bbox = font.getbbox(line)
        max_line_width = max(max_line_width, bbox[2] - bbox[0])
    overflow_ratio = max_line_width / box_w if box_w else 0

    hit_floor = chosen_size <= min_size
    if overflow_ratio > 1.05 or hit_floor:
        flags.append({
            "page": page_name,
            "block_index": block_index,
            "box": [x1, y1, x2, y2],
            "chosen_size": chosen_size,
            "overflow_ratio": round(overflow_ratio, 3),
            "hit_min_size": hit_floor,
            "reason": "overflow" if overflow_ratio > 1.05 else "min_size_floor"
        })

def assign_bubble_ids(page_stem, blocks):
    """TASK-21: stable bubble IDs for manual editing. Ranks blocks by
    (y1, x1) reading order for the ID *value* (so IDs are consistent
    across runs with the same detections, regardless of blk_list's
    internal order), but returns the ID list in the SAME order as the
    input `blocks` so callers can zip it against their own per-block loop."""
    indexed = list(enumerate(blocks))
    ranked = sorted(indexed, key=lambda pair: (pair[1].xyxy[1], pair[1].xyxy[0]))
    id_for_original_index = {}
    for rank, (orig_idx, blk) in enumerate(ranked):
        id_for_original_index[orig_idx] = f"{page_stem}_b{rank:02d}"
    return [id_for_original_index[i] for i in range(len(blocks))]

def write_bubbles_meta(book_dir, page_stem, entries):
    """TASK-21: writes book_dir/bubbles_meta/<page_stem>.json - one file
    per page, the source of truth the manual-edit overlay UI draws bubble
    bounding boxes and current text from."""
    meta_dir = os.path.join(book_dir, "bubbles_meta")
    os.makedirs(meta_dir, exist_ok=True)
    path = os.path.join(meta_dir, f"{page_stem}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return path

def match_bubbles_iou(old_entries, new_entries, iou_threshold=0.5):
    """TASK-21: reconciles bubble IDs across a page regeneration.
    dedupe_blocks (Stage A) can legitimately produce a different block
    count/order between runs, so a plain index-based ID would silently
    disconnect a pending edit from its bubble. Greedy best-IoU-first
    matching (each old bubble matched to at most one new bubble, and vice
    versa). Returns {old_id: new_id_or_None} - None means no confident
    match was found in the new set, so the caller should mark any edit
    referencing that old bubble as "orphaned" rather than silently
    dropping it."""
    candidates = []
    for old in old_entries:
        best_iou = 0.0
        best_new_id = None
        for new in new_entries:
            iou = _iou(old["bbox"], new["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_new_id = new["id"]
        candidates.append((best_iou, old["id"], best_new_id))
    # Strongest matches claim their target first, so a weak/ambiguous
    # match never steals a new bubble a stronger match also wanted.
    candidates.sort(key=lambda c: c[0], reverse=True)
    result = {}
    used_new = set()
    for iou, old_id, new_id in candidates:
        if new_id is not None and new_id not in used_new and iou > iou_threshold:
            result[old_id] = new_id
            used_new.add(new_id)
        else:
            result[old_id] = None
    return result

def translate_batch_llm(texts, source_lang, glossary, api_url, overrides=None):
    if not texts:
        return {}

    # TASK-21: texts with a human-edited override skip the LLM entirely -
    # both to avoid wasting a translation call and, more importantly, to
    # guarantee the human edit survives verbatim rather than risking the
    # LLM producing something different on a re-run.
    overrides = overrides or {}
    result = {txt: overrides[txt] for txt in texts if txt in overrides}
    remaining = [txt for txt in texts if txt not in overrides]
    if not remaining:
        return result

    # Construct terminology instructions from glossary
    glossary_rules = ""
    if glossary:
        glossary_rules = "Follow this terminology exactly:\n"
        for src_word, tgt_word in glossary.items():
            glossary_rules += f"- {src_word} -> {tgt_word}\n"

    prompt_list = "\n".join([f"{i+1}. {txt}" for i, txt in enumerate(remaining)])
    
    system_prompt = f"""You are a professional manga translator. Translate the following numbered list of texts from {source_lang.upper()} to Ukrainian.
Preserve context, sound effects (if present), informal spoken registers, character personalities, and sentence fragments.
Do NOT translate characters names if they are part of the glossary.
Maintain the exact same line-by-line numbering format. Output ONLY the translated list. No intro, no chat.
{glossary_rules}
"""

    try:
        response = requests.post(
            api_url,
            json={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_list}
                ],
                "temperature": 0.2
            },
            timeout=300
        )
        if response.status_code == 200:
            res_json = response.json()
            content = res_json["choices"][0]["message"]["content"].strip()
            lines = content.split("\n")

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if "." in line:
                    parts = line.split(".", 1)
                    try:
                        idx = int(parts[0].strip()) - 1
                        val = parts[1].strip()
                        if 0 <= idx < len(remaining):
                            result[remaining[idx]] = val
                    except ValueError:
                        continue

            # Fill missing translations with original text
            for txt in remaining:
                if txt not in result:
                    result[txt] = txt

            return result
        else:
            log(f"Error: API returned status code {response.status_code}: {response.text}")
    except Exception as e:
        log(f"Translation API request failed: {e}")

    # Fallback to returning original text if translation fails
    for txt in remaining:
        result.setdefault(txt, txt)
    return result

def process_page(img, page_basename, glossary, api_url, lang, detector, mocr, font_path, overrides=None):
    """TASK-21: runs the Stage A-E pipeline (detect -> dedupe -> OCR ->
    translate -> inpaint -> typeset -> post-check) on a single
    already-loaded page image. Pure image processing, no file I/O - both
    the full-book loop in main() and the single-page --regenerate-page
    path share this, so a manual edit's regen goes through exactly the
    same pipeline a fresh page does (fixes TASK-19_manga_typeset_autofix's
    "regen must go through the full A-E pipeline, not just typeset, or
    the ghost-text problem returns" requirement).

    overrides: optional {original_ocr_text: edited_translation} dict, see
    translate_batch_llm - lets a human edit survive a page regeneration
    verbatim instead of being re-translated by the LLM.

    Returns (final_img_bgr, cleaned_img_bgr, page_quality_flags,
    page_bubbles_meta). If no text bubbles are found/recognized,
    final_img_bgr and cleaned_img_bgr are both `img` untouched, and both
    lists are empty."""
    page_quality_flags = []
    page_bubbles_meta = []

    mask, mask_refined, blk_list = detector(img, refine_mode=REFINEMASK_INPAINT, keep_undetected_mask=True)
    blk_list = dedupe_blocks(blk_list)

    if not blk_list:
        return img, img, page_quality_flags, page_bubbles_meta

    page_ocr_texts = []
    block_crops = []
    h_img, w_img = img.shape[:2]

    if lang != 'ja':
        import pytesseract

    for blk in blk_list:
        x1, y1, x2, y2 = blk.xyxy
        # Add 5px padding for safer boundary OCR
        x1_pad = max(0, x1 - 5)
        y1_pad = max(0, y1 - 5)
        x2_pad = min(w_img, x2 + 5)
        y2_pad = min(h_img, y2 + 5)

        crop = img[y1_pad:y2_pad, x1_pad:x2_pad]
        if crop.size == 0:
            continue

        pil_crop = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))

        if lang == 'ja':
            txt = mocr(pil_crop).strip()
        else:
            txt = pytesseract.image_to_string(pil_crop, lang='eng', config='--psm 6').strip()

        txt = txt.replace("\n", " ").replace("\r", " ").strip()
        txt = " ".join(txt.split())

        if txt:
            page_ocr_texts.append(txt)
            block_crops.append((blk, txt))

    if not page_ocr_texts:
        return img, img, page_quality_flags, page_bubbles_meta

    translations = translate_batch_llm(page_ocr_texts, lang, glossary, api_url, overrides=overrides)

    # Stage B: larger radius + per-block flat-fill fallback for cases the
    # wider TELEA radius alone still leaves a "ghost" of the original
    # text under (bold/large source fonts).
    inpainted = robust_inpaint(img, mask_refined, blk_list)

    pil_img = Image.fromarray(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)

    page_stem = os.path.splitext(page_basename)[0]
    bubble_ids = assign_bubble_ids(page_stem, [blk for blk, _ in block_crops])

    for block_index, (blk, orig_txt) in enumerate(block_crops):
        translated_txt = translations.get(orig_txt, orig_txt)
        if not translated_txt:
            continue

        # Stage C: use the actual cleaned/masked region for this block
        # (padded) as the typeset box, instead of the OCR-tight blk.xyxy.
        x1, y1, x2, y2 = get_bubble_box(blk, mask_refined, img.shape)
        w_box = x2 - x1
        h_box = y2 - y1

        # Stage D: floor/ceiling-clamped font size, hyphenated hard-wrap.
        best_size, wrapped_lines = fit_text(translated_txt, font_path, w_box, h_box)
        draw_text_centered(draw, wrapped_lines, font_path, best_size, (x1, y1, x2, y2))

        # Stage E: flag anything that still looks wrong for later review.
        block_flags = []
        post_render_check(block_flags, page_basename, block_index, best_size, wrapped_lines,
                           (x1, y1, x2, y2), font_path, min_size=12)
        page_quality_flags.extend(block_flags)

        page_bubbles_meta.append({
            "id": bubble_ids[block_index],
            "bbox": [x1, y1, x2, y2],
            "original_text": orig_txt,
            "translated_text": translated_txt,
            "quality_flags": block_flags[0] if block_flags else {}
        })

    final_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return final_img, inpainted, page_quality_flags, page_bubbles_meta

def regenerate_single_page(args, glossary, detector, mocr):
    """TASK-21: re-runs the FULL A-E pipeline (process_page) on just one
    page, for a manual bubble-edit regen. Deliberately does NOT skip
    straight to typeset on the existing cleaned image - re-running
    detection/dedup/inpaint too means the TASK-20 fixes (ghost-text
    removal, deduped blocks) still apply to a regenerated page, not just
    a fresh one. Re-extracts the target page from the ORIGINAL source
    (same extract_manga_pages() path/PDF/CBZ/directory every normal run
    uses) rather than reading a persisted "source" copy, since archive
    sources are only ever extracted to a temp dir today - this keeps
    directory/CBZ/PDF sources all working uniformly with no special-casing.

    Prints a single JSON line to stdout on success:
    {"status": "success", "bubble_id_mapping": {old_id: new_id_or_null},
    "bubbles": [...new bubbles_meta entries...]} - kbg_web/app.py's
    regenerate-manga-page route parses this to reconcile pending edits
    (mark matched ones "regenerated", unmatched ones "orphaned")."""
    page_filename = args.regenerate_page

    overrides = {}
    if args.overrides_json and os.path.exists(args.overrides_json):
        try:
            with open(args.overrides_json, "r", encoding="utf-8") as f:
                overrides = json.load(f)
        except Exception as e:
            log(f"Warning: Failed to load overrides JSON: {e}")

    regen_temp_in = tempfile.mkdtemp()
    try:
        extract_manga_pages(args.input, regen_temp_in)
        page_path = os.path.join(regen_temp_in, page_filename)
        if not os.path.exists(page_path):
            log(f"Error: page '{page_filename}' not found after re-extracting source '{args.input}'.")
            print(json.dumps({"status": "error", "message": f"page '{page_filename}' not found in source"}))
            sys.exit(1)

        img = cv2.imread(page_path)
        if img is None:
            log(f"Error: failed to read page '{page_path}'.")
            print(json.dumps({"status": "error", "message": "failed to read page image"}))
            sys.exit(1)

        font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        if not os.path.exists(font_path):
            font_path = None

        final_img, cleaned_img, page_flags, new_bubbles = process_page(
            img, page_filename, glossary, args.api_url, args.lang, detector, mocr, font_path,
            overrides=overrides
        )

        book_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), ".."))
        page_stem = os.path.splitext(page_filename)[0]

        cleaned_dir = os.path.join(book_dir, "cleaned")
        translated_dir = os.path.join(book_dir, "translated")
        os.makedirs(cleaned_dir, exist_ok=True)
        os.makedirs(translated_dir, exist_ok=True)
        cv2.imwrite(os.path.join(cleaned_dir, page_filename), cleaned_img)
        cv2.imwrite(os.path.join(translated_dir, page_filename), final_img)

        # Load the OLD bubbles_meta.json snapshot BEFORE overwriting it,
        # so pending edits referencing old bubble IDs can be reconciled.
        meta_path = os.path.join(book_dir, "bubbles_meta", f"{page_stem}.json")
        old_bubbles = []
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    old_bubbles = json.load(f)
            except Exception:
                old_bubbles = []

        write_bubbles_meta(book_dir, page_stem, new_bubbles)
        id_mapping = match_bubbles_iou(old_bubbles, new_bubbles)

        # Update the book-wide quality_flags.json: replace only this
        # page's entries, leave every other page's flags untouched.
        quality_flags_path = os.path.join(book_dir, "quality_flags.json")
        all_flags = []
        if os.path.exists(quality_flags_path):
            try:
                with open(quality_flags_path, "r", encoding="utf-8") as f:
                    all_flags = json.load(f)
            except Exception:
                all_flags = []
        all_flags = [f for f in all_flags if f.get("page") != page_filename]
        all_flags.extend(page_flags)
        with open(quality_flags_path, "w", encoding="utf-8") as f:
            json.dump(all_flags, f, ensure_ascii=False, indent=2)

        log(f"Regenerated page '{page_filename}': {len(new_bubbles)} bubble(s), {len(page_flags)} quality flag(s).")
        print(json.dumps({"status": "success", "bubble_id_mapping": id_mapping, "bubbles": new_bubbles}, ensure_ascii=False))
    finally:
        shutil.rmtree(regen_temp_in, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="Manga translation pipeline (Segmentation -> OCR -> LLM translation -> Inpainting -> Typesetting)")
    parser.add_argument("--input", required=True, help="Path to input manga (PDF, CBZ, CBR, CB7, EPUB, or image folder)")
    parser.add_argument("--output", required=True, help="Path to output CBZ archive or directory")
    parser.add_argument("--lang", default="en", choices=["en", "ja"], help="Manga source language (en=English, ja=Japanese)")
    parser.add_argument("--glossary", help="Path to glossary.json file")
    parser.add_argument("--api-url", default="http://127.0.0.1:8081/v1/chat/completions", help="llama-server API Endpoint")
    parser.add_argument("--progress-file", help="Path to write progress JSON")
    parser.add_argument("--left-to-right", action="store_true", help="Set reading direction to LTR")
    parser.add_argument("--no-translate", action="store_true", help="Skip translation (copy original images)")
    parser.add_argument("--no-ebook", action="store_true", help="Skip AZW3 generation via Mapaki")
    parser.add_argument("--max-width", type=int, default=1280, help="Maximum width of pages (0 to disable)")
    parser.add_argument("--max-height", type=int, default=1920, help="Maximum height of pages (0 to disable)")
    parser.add_argument("--regenerate-page", help="TASK-21: re-run the full A-E pipeline on just this one page filename (manual bubble edit regen), instead of the whole book")
    parser.add_argument("--overrides-json", help="TASK-21: path to a JSON {original_ocr_text: edited_translation} map, used only with --regenerate-page")
    args = parser.parse_args()

    # Load glossary if provided
    glossary = {}
    if args.glossary and os.path.exists(args.glossary):
        try:
            with open(args.glossary, "r", encoding="utf-8") as f:
                glossary = json.load(f)
            log(f"Loaded glossary with {len(glossary)} entries.")
        except Exception as e:
            log(f"Warning: Failed to load glossary: {e}")

    # Set up models
    detector_model_path = download_detector_model()
    log("Initializing comic text detector...")
    detector = TextDetector(model_path=detector_model_path, device='cpu')
    
    mocr = None
    if args.lang == 'ja':
        log("Initializing Japanese Manga OCR...")
        from manga_ocr import MangaOcr
        mocr = MangaOcr()
    else:
        log("Using Tesseract OCR for English...")
        import pytesseract

    if args.regenerate_page:
        regenerate_single_page(args, glossary, detector, mocr)
        return

    # Create temporary directories for processing
    temp_in = tempfile.mkdtemp()
    temp_out = tempfile.mkdtemp()

    try:
        # Extract source manga to temporary folder
        extract_manga_pages(args.input, temp_in)
        pages = natsorted([os.path.join(temp_in, f) for f in os.listdir(temp_in) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
        
        if not pages:
            log("No pages/images found in input.")
            return

        log(f"Processing {len(pages)} pages...")
        
        font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        if not os.path.exists(font_path):
            font_path = None # Pillow will fall back to default font if not found

        pages_to_process = [] if args.no_translate else pages
        quality_flags = []  # Stage E: accumulated across all pages, written to quality_flags.json at the end

        if args.no_translate:
            log("No-translate mode: copying already translated images to output...")
            translated_dir = None
            if args.output.lower().endswith('.cbz'):
                translated_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "translated"))
            for page_path in pages:
                basename = os.path.basename(page_path)
                copied = False
                if translated_dir:
                    possible_translated = os.path.join(translated_dir, basename)
                    if os.path.exists(possible_translated):
                        shutil.copy2(possible_translated, os.path.join(temp_out, basename))
                        copied = True
                if not copied:
                    # Fallback to original image if not translated yet
                    shutil.copy2(page_path, os.path.join(temp_out, basename))

        for idx, page_path in enumerate(pages_to_process):
            log(f"Page {idx+1}/{len(pages_to_process)}: {os.path.basename(page_path)}")
            
            basename = os.path.basename(page_path)
            # Resume logic: check if already translated
            translated_path = None
            if args.output.lower().endswith('.cbz'):
                translated_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "translated"))
                cleaned_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "cleaned"))
                possible_translated = os.path.join(translated_dir, basename)
                if os.path.exists(possible_translated):
                    translated_path = possible_translated
                    
            if translated_path:
                log(f"Page {idx+1} already translated. Skipping.")
                # Copy to temp_out
                shutil.copy2(translated_path, os.path.join(temp_out, basename))
                # Make sure it's in cleaned_dir
                possible_cleaned = os.path.join(cleaned_dir, basename)
                if not os.path.exists(possible_cleaned):
                    shutil.copy2(translated_path, possible_cleaned)
                continue

            if args.progress_file:
                try:
                    with open(args.progress_file, "w", encoding="utf-8") as pf:
                        json.dump({"current_page": idx + 1, "total_pages": len(pages)}, pf)
                except Exception:
                    pass
            img = cv2.imread(page_path)
            if img is None:
                log(f"Warning: Failed to read page {page_path}")
                continue
                
            final_img, cleaned_img, page_flags, page_bubbles = process_page(
                img, basename, glossary, args.api_url, args.lang, detector, mocr, font_path
            )
            quality_flags.extend(page_flags)

            if not page_bubbles:
                log("No text bubbles found/recognized. Copying original page.")

            cv2.imwrite(os.path.join(temp_out, basename), final_img)

            if args.output.lower().endswith('.cbz'):
                cleaned_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "cleaned"))
                os.makedirs(cleaned_dir, exist_ok=True)
                cv2.imwrite(os.path.join(cleaned_dir, basename), cleaned_img)

                if page_bubbles:
                    translated_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "translated"))
                    os.makedirs(translated_dir, exist_ok=True)
                    cv2.imwrite(os.path.join(translated_dir, basename), final_img)

                    # TASK-21: per-page bubble metadata for the manual-edit
                    # overlay UI (bbox + current text + quality flags).
                    book_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), ".."))
                    page_stem = os.path.splitext(basename)[0]
                    write_bubbles_meta(book_dir, page_stem, page_bubbles)

        # Stage E: write accumulated quality flags for this book, a future
        # input for a manual-review queue (not built in this pass).
        if quality_flags:
            book_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), ".."))
            quality_flags_path = os.path.join(book_dir, "quality_flags.json")
            try:
                with open(quality_flags_path, "w", encoding="utf-8") as f:
                    json.dump(quality_flags, f, ensure_ascii=False, indent=2)
                log(f"Wrote {len(quality_flags)} quality flag(s) to {quality_flags_path}")
            except Exception as e:
                log(f"Warning: Failed to write quality_flags.json: {e}")

        # Downscale images if they exceed maximum dimensions to prevent blank page bugs
        if args.max_height > 0 or args.max_width > 0:
            log(f"Preprocessing translated images (fitting into max dimensions {args.max_width}x{args.max_height})...")
            for f in os.listdir(temp_out):
                fpath = os.path.join(temp_out, f)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and os.path.isfile(fpath):
                    try:
                        with Image.open(fpath) as img_pil:
                            width, height = img_pil.size
                            need_resize = False
                            new_width = width
                            new_height = height
                            
                            # Check height boundary
                            if args.max_height > 0 and height > args.max_height:
                                need_resize = True
                                ratio = args.max_height / height
                                new_height = args.max_height
                                new_width = int(width * ratio)
                            
                            # Check width boundary on scaled dimensions
                            if args.max_width > 0 and new_width > args.max_width:
                                need_resize = True
                                ratio = args.max_width / new_width
                                new_width = args.max_width
                                new_height = int(new_height * ratio)
                                
                            if need_resize:
                                log(f"Downscaling {f} from {width}x{height} to {new_width}x{new_height}")
                                img_pil = img_pil.resize((new_width, new_height), Image.Resampling.LANCZOS)
                                img_pil.save(fpath)
                    except Exception as ex:
                        log(f"Warning: Failed to downscale image {f}: {ex}")

        # Packaging processed pages
        if args.output.lower().endswith('.cbz'):
            log(f"Packaging pages into CBZ archive: {args.output}")
            shutil.make_archive(args.output[:-4], 'zip', temp_out)
            shutil.move(args.output[:-4] + '.zip', args.output)

            # Generate AZW3 using Mapaki
            mapaki_bin = shutil.which("mapaki")
            if not mapaki_bin:
                for possible_path in ["/root/go/bin/mapaki", os.path.expanduser("~/go/bin/mapaki"), "/usr/local/bin/mapaki"]:
                    if os.path.exists(possible_path):
                        mapaki_bin = possible_path
                        break

            if mapaki_bin and not args.no_ebook:
                azw3_output = args.output[:-4] + ".azw3"
                log(f"Generating AZW3 using Mapaki: {azw3_output}")

                title = os.path.splitext(os.path.basename(args.output))[0]
                clean_title = title.replace('_', ' ').replace('-', ' ').title()

                cmd = [
                    mapaki_bin,
                    "-i", temp_out,
                    "-o", azw3_output,
                    "--title", clean_title
                ]
                if args.left_to_right:
                    cmd.append("--left-to-right")

                try:
                    log(f"Running Mapaki: {' '.join(cmd)}")
                    subprocess.run(cmd, check=True)
                    log(f"AZW3 manga generated successfully at: {azw3_output}")
                except Exception as e:
                    log(f"Error running Mapaki: {e}")
            else:
                log("Mapaki executable not found. Skipping AZW3 generation.")
        else:
            log(f"Saving pages to directory: {args.output}")
            os.makedirs(args.output, exist_ok=True)
            for f in os.listdir(temp_out):
                shutil.copy(os.path.join(temp_out, f), os.path.join(args.output, f))
                
        if args.progress_file:
            try:
                with open(args.progress_file, "w", encoding="utf-8") as pf:
                    json.dump({"current_page": len(pages), "total_pages": len(pages)}, pf)
            except Exception:
                pass
        log("Manga translation completed successfully!")
        
    finally:
        # Clean temporary directories
        shutil.rmtree(temp_in, ignore_errors=True)
        shutil.rmtree(temp_out, ignore_errors=True)

if __name__ == "__main__":
    main()
