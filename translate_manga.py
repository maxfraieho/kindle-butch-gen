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
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def fit_text(text, font_path, max_width, max_height):
    # Binary search for optimal font size
    low = 8
    high = 80
    best_size = low
    best_lines = [text]
    
    while low <= high:
        mid = (low + high) // 2
        try:
            font = ImageFont.truetype(font_path, mid)
        except Exception:
            font = ImageFont.load_default()
        
        lines = wrap_text(text, font, max_width)
        
        # Calculate total height and max line width
        total_height = 0
        max_line_width = 0
        for line in lines:
            bbox = font.getbbox(line)
            line_height = bbox[3] - bbox[1]
            line_width = bbox[2] - bbox[0]
            total_height += line_height + 2
            if line_width > max_line_width:
                max_line_width = line_width
                
        if total_height <= max_height and max_line_width <= max_width:
            best_size = mid
            best_lines = lines
            low = mid + 1
        else:
            high = mid - 1
            
    return best_size, best_lines

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

def translate_batch_llm(texts, source_lang, glossary, api_url):
    if not texts:
        return {}
        
    # Construct terminology instructions from glossary
    glossary_rules = ""
    if glossary:
        glossary_rules = "Follow this terminology exactly:\n"
        for src_word, tgt_word in glossary.items():
            glossary_rules += f"- {src_word} -> {tgt_word}\n"
            
    prompt_list = "\n".join([f"{i+1}. {txt}" for i, txt in enumerate(texts)])
    
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
            result = {}
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
                        if 0 <= idx < len(texts):
                            result[texts[idx]] = val
                    except ValueError:
                        continue
            
            # Fill missing translations with original texts
            for txt in texts:
                if txt not in result:
                    result[txt] = txt
                    
            return result
        else:
            log(f"Error: API returned status code {response.status_code}: {response.text}")
    except Exception as e:
        log(f"Translation API request failed: {e}")
        
    # Fallback to returning original text if translation fails
    return {txt: txt for txt in texts}


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
                
            # Run text detector
            mask, mask_refined, blk_list = detector(img, refine_mode=REFINEMASK_INPAINT, keep_undetected_mask=True)
            
            if not blk_list:
                log("No text bubbles found. Copying original page.")
                cv2.imwrite(os.path.join(temp_out, os.path.basename(page_path)), img)
                continue
                
            # Perform OCR on text bubble crops
            page_ocr_texts = []
            block_crops = []
            h_img, w_img = img.shape[:2]
            
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
                
                # Run OCR
                if args.lang == 'ja':
                    txt = mocr(pil_crop).strip()
                else:
                    txt = pytesseract.image_to_string(pil_crop, lang='eng', config='--psm 6').strip()
                
                # Cleanup text format
                txt = txt.replace("\n", " ").replace("\r", " ").strip()
                # Remove extra spaces
                txt = " ".join(txt.split())
                
                if txt:
                    page_ocr_texts.append(txt)
                    block_crops.append((blk, txt))
                    
            if not page_ocr_texts:
                log("No text recognized. Copying original page.")
                cv2.imwrite(os.path.join(temp_out, os.path.basename(page_path)), img)
                if args.output.lower().endswith('.cbz'):
                    cleaned_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "cleaned"))
                    os.makedirs(cleaned_dir, exist_ok=True)
                    cv2.imwrite(os.path.join(cleaned_dir, os.path.basename(page_path)), img)
                continue
                
            # Translate recognized texts
            translations = translate_batch_llm(page_ocr_texts, args.lang, glossary, args.api_url)
            
            # Clean image (Inpaint original text bubbles using mask)
            inpainted = cv2.inpaint(img, mask_refined, 3, cv2.INPAINT_TELEA)
            if args.output.lower().endswith('.cbz'):
                cleaned_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "cleaned"))
                os.makedirs(cleaned_dir, exist_ok=True)
                cv2.imwrite(os.path.join(cleaned_dir, os.path.basename(page_path)), inpainted)
            
            # Typeset translated text back onto bubble
            pil_img = Image.fromarray(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(pil_img)
            
            for blk, orig_txt in block_crops:
                translated_txt = translations.get(orig_txt, orig_txt)
                if not translated_txt:
                    continue
                    
                x1, y1, x2, y2 = blk.xyxy
                w_box = x2 - x1
                h_box = y2 - y1
                
                # Find optimal font size and wrapped lines
                best_size, wrapped_lines = fit_text(translated_txt, font_path, w_box, h_box)
                
                # Render centered text
                draw_text_centered(draw, wrapped_lines, font_path, best_size, (x1, y1, x2, y2))
                
            # Convert back to cv2 BGR format and save
            final_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            cv2.imwrite(os.path.join(temp_out, os.path.basename(page_path)), final_img)
            
            # Copy typeset image to translated directory in real-time
            if args.output.lower().endswith('.cbz'):
                translated_dir = os.path.abspath(os.path.join(os.path.dirname(args.output), "..", "translated"))
                os.makedirs(translated_dir, exist_ok=True)
                cv2.imwrite(os.path.join(translated_dir, os.path.basename(page_path)), final_img)
            
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
