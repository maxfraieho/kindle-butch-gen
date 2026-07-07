#!/usr/bin/env python3
import sys
import os
import shutil
import subprocess
import argparse
import json
from datetime import datetime

# Add the repo root to sys.path so we can import from common
repo_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, repo_dir)

from common.book_paths import resolve_book_paths
from common.epub_validate import validate_epub

def log(message, log_path):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{timestamp}] {message}\n"
    print(msg, end="", flush=True)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg)
    except Exception as e:
        print(f"Failed to write to log path {log_path}: {e}")

def run_marker_batch(start, end, pdf_path, batches_dir, log_path):
    log(f"Starting marker batch {start}-{end}...", log_path)
    batch_out_dir = os.path.join(batches_dir, f"batch_{start}_{end}")
    
    cmd = [
        "proot-distro", "login", "ubuntu", "--",
        "env",
        "OMP_NUM_THREADS=4",
        "MKL_NUM_THREADS=4",
        "OPENBLAS_NUM_THREADS=4",
        "TORCH_NUM_THREADS=4",
        "marker_single",
        pdf_path,
        "--disable_ocr",
        "--disable_multiprocessing",
        "--page_range", f"{start}-{end}",
        "--output_dir", batch_out_dir
    ]
    
    # Run the process
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # Save marker log
    os.makedirs(batch_out_dir, exist_ok=True)
    marker_log_path = os.path.join(batch_out_dir, "marker_run.log")
    with open(marker_log_path, "w", encoding="utf-8") as log_file:
        log_file.write(result.stdout)
        
    if result.returncode != 0:
        log(f"Error: Batch {start}-{end} failed with return code {result.returncode}!", log_path)
        log("Last 10 lines of marker output:\n" + "\n".join(result.stdout.splitlines()[-10:]), log_path)
        return False
    
    log(f"Batch {start}-{end} completed successfully.", log_path)
    return True

def main():
    parser = argparse.ArgumentParser(description="Batch conversion, translation, and ebook generation pipeline")
    parser.add_argument("--book", "-b", required=True, help="Book slug")
    parser.add_argument("--config", "-c", help="Optional path to config.json")
    parser.add_argument("--clean", action="store_true", help="Clean batches directory before running")
    parser.add_argument("--no-translate", action="store_true", help="Disable translation stage")
    parser.add_argument("--no-ebook", action="store_true", help="Disable Calibre EPUB/AZW3 conversion")
    parser.add_argument("--no-audio", action="store_true", help="Disable audiobook synthesis stage")
    args = parser.parse_args()

    slug = args.book
    
    # Load paths using resolve_book_paths
    paths = resolve_book_paths(repo_dir, slug, config_path=args.config)
    log_path = paths["log_path"]
    
    # If custom config is provided, overwrite key fields in paths
    if args.config and os.path.exists(args.config):
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                custom_cfg = json.load(f)
            log(f"Overriding book paths with custom config from {args.config}", log_path)
            for k, v in custom_cfg.items():
                if k in ["title", "authors", "target_lang", "source_lang", "page_ranges", "generate_audiobook", "tts_voice", "tts_voice_quality"]:
                    paths[k] = v
                elif k == "pdf_path":
                    paths["pdf_path"] = os.path.abspath(v)
                elif k == "cover":
                    cover_path = v
                    if not os.path.isabs(cover_path):
                        cover_path = os.path.join(paths["book_dir"], cover_path)
                    paths["cover_path"] = os.path.abspath(cover_path)
        except Exception as e:
            log(f"Warning: Failed to parse custom config: {e}", log_path)
            
    log(f"=== Starting pipeline for book: {slug} ===", log_path)
    
    pdf_path = paths.get("pdf_path")
    has_pdf = pdf_path and os.path.exists(pdf_path)
    
    os.makedirs(paths["batches_dir"], exist_ok=True)
    os.makedirs(paths["translated_dir"], exist_ok=True)
    os.makedirs(paths["output_dir"], exist_ok=True)
    
    suffix = f"_translated_{paths['target_lang']}" if (paths["target_lang"] != paths["source_lang"] and not args.no_translate) else ""
    if suffix:
        merged_md_name = f"merged_translated_{paths['target_lang']}.md"
    else:
        merged_md_name = f"merged_source_{paths['source_lang']}.md"
    final_merged_md_path = os.path.join(paths["translated_dir"], merged_md_name)

    if not has_pdf:
        log("No source PDF found or configured. Checking for existing merged files...", log_path)
        source_md_name = f"merged_source_{paths['source_lang']}.md"
        source_md_path = os.path.join(paths["translated_dir"], source_md_name)
        
        should_translate = (paths["target_lang"] != paths["source_lang"]) and not args.no_translate
        
        if should_translate:
            if not os.path.exists(final_merged_md_path):
                if os.path.exists(source_md_path):
                    log(f"Merged source Markdown exists at '{source_md_path}'. Translating to '{final_merged_md_path}'...", log_path)
                    cmd_translate = [
                        "python3", os.path.join(repo_dir, "translate_stage.py"),
                        "--input", source_md_path,
                        "--output", final_merged_md_path,
                        "--cache", paths["translate_cache"],
                        "--target-lang", paths["target_lang"],
                        "--book", slug
                    ]
                    if args.config:
                        cmd_translate.extend(["--config", args.config])
                    log(f"Running translation command: {' '.join(cmd_translate)}", log_path)
                    res_trans = subprocess.run(cmd_translate)
                    if res_trans.returncode != 0:
                        log("Error: Translation of merged source markdown failed!", log_path)
                        sys.exit(1)
                else:
                    log(f"Error: Target translated markdown '{final_merged_md_path}' does not exist, and no source markdown '{source_md_path}' found.", log_path)
                    sys.exit(1)
        else:
            # No translation needed, make sure the file is in final_merged_md_path
            if not os.path.exists(final_merged_md_path):
                if os.path.exists(source_md_path):
                    shutil.copy2(source_md_path, final_merged_md_path)
                else:
                    log(f"Error: Neither target markdown '{final_merged_md_path}' nor source markdown '{source_md_path}' exists.", log_path)
                    sys.exit(1)
        log("Merged Markdown is ready. Skipping extraction stage.", log_path)
    else:
        log(f"PDF Path: {pdf_path}", log_path)
        log(f"Output Directory: {paths['output_dir']}", log_path)
        
        # Clean batches if requested
        if args.clean and os.path.exists(paths["batches_dir"]):
            log(f"Cleaning batches directory: {paths['batches_dir']}", log_path)
            shutil.rmtree(paths["batches_dir"])
            os.makedirs(paths["batches_dir"], exist_ok=True)
            
        pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]
        
        page_ranges = paths.get("page_ranges")
        if not page_ranges:
            log("Warning: No page_ranges defined in config.json. Pipeline cannot run batches.", log_path)
            sys.exit(1)
            
        success = True
        
        # 1. Run marker single-page extraction for each range
        for start, end in page_ranges:
            batch_out_dir = os.path.join(paths["batches_dir"], f"batch_{start}_{end}")
            marker_out_subdir = os.path.join(batch_out_dir, pdf_basename)
            marker_md_file = os.path.join(marker_out_subdir, f"{pdf_basename}.md")
            
            if os.path.exists(marker_md_file) and os.path.getsize(marker_md_file) > 0:
                log(f"Marker batch {start}-{end} already completed. Skipping extraction.", log_path)
            else:
                if not run_marker_batch(start, end, pdf_path, paths["batches_dir"], log_path):
                    success = False
                    break
                    
            # 2. Run translation stage if target_lang != source_lang and not disabled
            should_translate = (paths["target_lang"] != paths["source_lang"]) and not args.no_translate
            if should_translate:
                translated_batch_md = os.path.join(marker_out_subdir, f"{pdf_basename}_translated_{paths['target_lang']}.md")
                if os.path.exists(translated_batch_md) and os.path.getsize(translated_batch_md) > 0:
                    log(f"Translated batch {start}-{end} already exists. Skipping translation.", log_path)
                else:
                    log(f"Translating batch {start}-{end} to {paths['target_lang']}...", log_path)
                    cmd_translate = [
                        "python3", os.path.join(repo_dir, "translate_stage.py"),
                        "--input", marker_md_file,
                        "--output", translated_batch_md,
                        "--cache", paths["translate_cache"],
                        "--target-lang", paths["target_lang"],
                        "--book", slug
                    ]
                    if args.config:
                        cmd_translate.extend(["--config", args.config])
                    log(f"Running translation command: {' '.join(cmd_translate)}", log_path)
                    res_trans = subprocess.run(cmd_translate)
                    if res_trans.returncode != 0:
                        log(f"Error: Translation of batch {start}-{end} failed!", log_path)
                        success = False
                        break
                        
        if not success:
            log("Pipeline aborted due to batch extraction/translation failures.", log_path)
            sys.exit(1)
            
        # 3. Merge batch markdown files and copy images
        log("Merging batch results...", log_path)
        merged_md_content = []
        
        for start, end in page_ranges:
            batch_out_dir = os.path.join(paths["batches_dir"], f"batch_{start}_{end}")
            marker_out_subdir = os.path.join(batch_out_dir, pdf_basename)
            md_file = os.path.join(marker_out_subdir, f"{pdf_basename}{suffix}.md")
            
            if not os.path.exists(md_file):
                log(f"Warning: Expected batch markdown file '{md_file}' not found. Skipping in merge.", log_path)
                continue
                
            # Copy images
            if os.path.exists(marker_out_subdir):
                for item in os.listdir(marker_out_subdir):
                    if item.lower().endswith((".jpeg", ".jpg", ".png", ".gif")):
                        src_img = os.path.join(marker_out_subdir, item)
                        dst_img = os.path.join(paths["translated_dir"], item)
                        shutil.copy2(src_img, dst_img)
                        
            # Read content
            with open(md_file, "r", encoding="utf-8") as f:
                merged_md_content.append(f.read())
                
        with open(final_merged_md_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(merged_md_content))
            
        log(f"Merged markdown saved to: {final_merged_md_path}", log_path)
    
    # 4. Convert merged markdown to EPUB and AZW3 using Calibre's ebook-convert
    if not args.no_ebook:
        lang_code = paths["target_lang"] if suffix else paths["source_lang"]
        lang_locale = "ru_RU.UTF-8" if lang_code == "ru" else f"{lang_code}_{lang_code.upper()}.UTF-8"
        
        epub_out_path = os.path.join(paths["output_dir"], f"{slug}_translated_{lang_code}.epub" if suffix else f"{slug}_source_{lang_code}.epub")
        azw3_out_path = os.path.join(paths["output_dir"], f"{slug}_translated_{lang_code}.azw3" if suffix else f"{slug}_source_{lang_code}.azw3")
        
        # EPUB conversion
        log(f"Converting merged markdown to EPUB: {epub_out_path}...", log_path)
        cmd_epub = [
            "proot-distro", "login", "ubuntu", "--",
            "env",
            f"LANG={lang_locale}",
            f"LC_ALL={lang_locale}",
            "ebook-convert",
            final_merged_md_path,
            epub_out_path,
            "--epub-version=2",
            f"--language={lang_code}",
            f"--title={paths['title']}",
            f"--authors={paths['authors']}"
        ]
        if os.path.exists(paths["cover_path"]):
            cmd_epub.append(f"--cover={paths['cover_path']}")
            
        env = os.environ.copy()
        env["LANG"] = lang_locale
        env["LC_ALL"] = lang_locale
        
        res_epub = subprocess.run(cmd_epub, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if not os.path.exists(epub_out_path):
            log("Error: Calibre EPUB generation failed!", log_path)
            log(res_epub.stdout, log_path)
            sys.exit(1)
            
        # EPUB Validation
        def epub_log(msg):
            log(msg, log_path)
            
        if not validate_epub(epub_out_path, epub_log):
            log("Error: Generated EPUB failed post-generation validation!", log_path)
            sys.exit(1)
            
        log("EPUB generated and validated successfully.", log_path)
        
        # AZW3 conversion
        log(f"Converting merged markdown to AZW3: {azw3_out_path}...", log_path)
        cmd_azw = [
            "proot-distro", "login", "ubuntu", "--",
            "env",
            f"LANG={lang_locale}",
            f"LC_ALL={lang_locale}",
            "ebook-convert",
            final_merged_md_path,
            azw3_out_path,
            f"--language={lang_code}",
            f"--title={paths['title']}",
            f"--authors={paths['authors']}"
        ]
        if os.path.exists(paths["cover_path"]):
            cmd_azw.append(f"--cover={paths['cover_path']}")
            
        res_azw = subprocess.run(cmd_azw, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if not os.path.exists(azw3_out_path):
            log("Error: Calibre AZW3 generation failed!", log_path)
            log(res_azw.stdout, log_path)
            sys.exit(1)
            
        log("AZW3 generated successfully.", log_path)
        
        # Copy to /sdcard/Download if exists/accessible
        sdcard_download_dir = "/sdcard/Download"
        if os.path.exists(sdcard_download_dir):
            try:
                shutil.copy2(epub_out_path, os.path.join(sdcard_download_dir, os.path.basename(epub_out_path)))
                shutil.copy2(azw3_out_path, os.path.join(sdcard_download_dir, os.path.basename(azw3_out_path)))
                log(f"Copied EPUB/AZW3 files to {sdcard_download_dir}.", log_path)
            except Exception as e:
                log(f"Warning: Failed to copy outputs to {sdcard_download_dir}: {e}", log_path)
                
    # 5. Audiobook generation
    if paths["generate_audiobook"] and not args.no_audio:
        log("Triggering audio stage synthesis...", log_path)
        cmd_audio = [
            "python3", os.path.join(repo_dir, "audio_stage.py"),
            "--book", slug
        ]
        if args.config:
            cmd_audio.extend(["--config", args.config])
        res_audio = subprocess.run(cmd_audio)
        if res_audio.returncode != 0:
            log("Error: Audiobook generation stage failed!", log_path)
            sys.exit(1)
            
        # Copy MP3 to /sdcard/Download if exists
        lang_code = paths["target_lang"] if suffix else paths["source_lang"]
        mp3_filename = f"{slug}_translated_{lang_code}.mp3"
        mp3_out_path = os.path.join(paths["output_dir"], mp3_filename)
        
        sdcard_download_dir = "/sdcard/Download"
        if os.path.exists(sdcard_download_dir) and os.path.exists(mp3_out_path):
            try:
                shutil.copy2(mp3_out_path, os.path.join(sdcard_download_dir, mp3_filename))
                log(f"Copied MP3 audiobook file to {sdcard_download_dir}.", log_path)
            except Exception as e:
                log(f"Warning: Failed to copy audiobook to {sdcard_download_dir}: {e}", log_path)
                
    log("=== Pipeline run fully completed successfully! ===", log_path)

if __name__ == "__main__":
    main()
