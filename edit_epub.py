import os
import sys
import re
import json
import zipfile
import tempfile
import shutil
import hashlib
import argparse
import requests
import xml.etree.ElementTree as ET
from common.text_protect import PlaceholderManager
from common.book_paths import resolve_book_paths

def log(message):
    print(f"[EPUB-Edit] {message}")

def get_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def to_bracket_format(text):
    prefix_map = {
        "IMAGE_LINE": "img",
        "CODE_BLOCK": "code",
        "MATH_BLOCK": "math",
        "MATH_INLINE": "mi",
        "INLINE_CODE": "ic",
        "LINK_URL": "link",
        "RAW_URL": "url",
        "HTML_TAG": "tag"
    }
    def repl(match):
        prefix = match.group(1)
        num = match.group(2)
        short = prefix_map.get(prefix, "t")
        return f"[{short}{num}]"
    return re.sub(r"__([A-Z_]+?)_(\d+)__", repl, text)

def to_prefix_format(text, pm):
    def repl(match):
        num = match.group(2)
        suffix = f"_{num}__"
        for key in pm.placeholders.keys():
            if key.endswith(suffix):
                return key
        return match.group(0)
    return re.sub(r"\[\s*([a-zA-Z]+)[-_\s]*(\d+)\s*\]", repl, text)

def edit_text(text, api_url, temperature=0.1):
    prompt = (
        "Виконай роль професійного редактора української мови. Виправ граматичні, орфографічні, пунктуаційні помилки, кальки з англійської мови та русизми у наданому тексті.\n"
        "Суворі правила обробки:\n"
        "1. Вихідний текст має повністю відповідати вхідному за змістом. Допускаються лише мінімальні правки для забезпечення правильності мови.\n"
        "2. Категорично заборонено змінювати, видаляти або переміщувати будь-які службові мітки та теги у квадратних дужках, такі як [tag1], [link2], [placeholder] тощо. Збережи їх у точності так, як вони вказані у вхідному тексті.\n"
        "3. Поверни виключно виправлений текст без будь-яких додаткових пояснень, вступних слів чи коментарів.\n\n"
        f"Вхідний текст для редагування:\n{text}"
    )
    
    headers = {"Content-Type": "application/json"}
    data = {
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": 1.0,
        "max_tokens": 2048
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=120)
        if response.status_code != 200:
            log(f"Error from llama-server: {response.status_code} - {response.text}")
            return None
        res_json = response.json()
        edited = res_json["choices"][0]["message"]["content"].strip()
        
        # Clean helper prefixes if the model added them
        clean_prefixes = [
            "ось відредагований текст:",
            "відредагований текст:",
            "виправлений текст:",
            "ось виправлений текст:"
        ]
        for pref in clean_prefixes:
            if edited.lower().startswith(pref):
                edited = edited[len(pref):].strip()
        return edited
    except Exception as e:
        log(f"API request failed: {e}")
        return None

def validate_editing_segment(original, edited):
    # Check placeholders matching
    orig_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", original))
    trans_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", edited))
    
    missing = orig_placeholders - trans_placeholders
    extra = trans_placeholders - orig_placeholders
    
    if missing or extra:
        log("Validation failure: Placeholders mismatch during editing!")
        log(f"Original segment: {original!r}")
        log(f"Edited segment: {edited!r}")
        if missing:
            log(f"Missing in edited: {missing}")
        if extra:
            log(f"Extra in edited: {extra}")
        return False
    return True

def edit_segment_with_retry(segment, pm, api_url, max_retries=2):
    temp = 0.1
    bracket_segment = to_bracket_format(segment)
    orig_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", segment))
    last_edited = None
    
    for attempt in range(max_retries):
        if attempt > 0:
            temp = 0.2
            log(f"Retrying editing of segment (attempt {attempt+1}/{max_retries}) with temperature {temp}...")
            
        edited = edit_text(bracket_segment, api_url, temperature=temp)
        if not edited:
            continue
            
        edited = to_prefix_format(edited, pm)
        edited = pm.normalize_placeholders(edited)
        
        last_edited = edited
            
        if validate_editing_segment(segment, edited):
            return edited
        else:
            log(f"Segment validation failed on attempt {attempt+1}.")
            
    # Rescue logic
    if last_edited:
        trans_placeholders = set(re.findall(r"__[A-Z_]+_[0-9]+__", last_edited))
        missing = orig_placeholders - trans_placeholders
        extra = trans_placeholders - orig_placeholders
        
        rescued = last_edited
        if extra:
            log(f"Stripping extra placeholders: {extra}")
            for ex in extra:
                rescued = rescued.replace(ex, "")
        if missing:
            log(f"Appending missing placeholders: {missing}")
            rescued = rescued + " " + " ".join(sorted(list(missing)))
            
        if validate_editing_segment(segment, rescued):
            return rescued
            
    log("Warning: Segment validation failed after all retries. Keeping translated version.")
    return segment

def register_namespaces():
    ET.register_namespace('', 'http://www.w3.org/1999/xhtml')
    ET.register_namespace('opf', 'http://www.idpf.org/2007/opf')
    ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
    ET.register_namespace('container', 'urn:oasis:names:tc:opendocument:xmlns:container')

def sanitize_xhtml_for_xml_parser(xml_bytes):
    try:
        content_str = xml_bytes.decode('utf-8')
    except Exception:
        content_str = xml_bytes.decode('latin-1')
        
    replacements = {
        'nbsp': '#160', 'copy': '#169', 'reg': '#174', 'trade': '#8482',
        'amp': '#38', 'lt': '#60', 'gt': '#62', 'quot': '#34', 'apos': '#39',
        'mdash': '#8212', 'ndash': '#8211', 'hellip': '#8230', 'ldquo': '#8220',
        'rdquo': '#8221', 'lsquo': '#8216', 'rsquo': '#8217', 'bull': '#8226',
        'middot': '#183'
    }
    def replace_entity(match):
        entity = match.group(1)
        if entity in replacements:
            return f"&{replacements[entity]};"
        if entity.startswith('#'):
            return match.group(0)
        return ' '
    sanitized = re.sub(r'&([a-zA-Z0-9#]+);', replace_entity, content_str)
    return sanitized

def main():
    parser = argparse.ArgumentParser(description="Ukrainian EPUB editing/proofreading pipeline tool")
    parser.add_argument("--input", "-i", required=True, help="Path to input translated EPUB file")
    parser.add_argument("--output", "-o", required=True, help="Path to output edited EPUB file")
    parser.add_argument("--api-url", default="http://localhost:8081/v1/chat/completions", help="Llama-server API URL")
    parser.add_argument("--cache", default=None, help="Path to JSON cache file")
    parser.add_argument("--book", "-b", required=True, help="Book slug")
    args = parser.parse_args()
    
    register_namespaces()
    
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    paths = resolve_book_paths(repo_dir, args.book)
    
    cache_path = args.cache
    if not cache_path:
        cache_path = os.path.join(paths["cache_dir"], "edit_cache.json")
        
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
    
    if not os.path.exists(args.input):
        log(f"Error: Input file '{args.input}' does not exist.")
        sys.exit(1)
        
    # Verify API
    try:
        r = requests.get(args.api_url.replace("/v1/chat/completions", "/health"), timeout=5)
        if r.status_code == 200:
            log(f"Connected to editing server at {args.api_url}")
        else:
            log(f"Warning: Health check failed: {r.status_code}")
    except Exception as e:
        log(f"Error: Could not connect to API server: {e}")
        sys.exit(1)
        
    # Load cache
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as cf:
                cache = json.load(cf)
            log(f"Loaded edit cache from {cache_path} with {len(cache)} entries.")
        except Exception as e:
            log(f"Warning: Failed to load cache: {e}. Starting fresh.")
            
    temp_dir = os.path.join(paths["book_dir"], "temp_epub_edit")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    log(f"Extracting EPUB to temporary directory: {temp_dir}")
    try:
        with zipfile.ZipFile(args.input, "r") as z:
            z.extractall(temp_dir)
    except Exception as e:
        log(f"Error: Failed to extract EPUB file: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(1)
        
    # Find OPF
    container_xml = os.path.join(temp_dir, "META-INF", "container.xml")
    if not os.path.exists(container_xml):
        log("Error: container.xml not found.")
        shutil.rmtree(temp_dir)
        sys.exit(1)
        
    tree = ET.parse(container_xml)
    root = tree.getroot()
    rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
    if rootfile is None:
        log("Error: rootfile element not found in container.xml.")
        shutil.rmtree(temp_dir)
        sys.exit(1)
        
    opf_rel_path = rootfile.attrib.get("full-path")
    opf_path = os.path.join(temp_dir, opf_rel_path)
    opf_dir = os.path.dirname(opf_path)
    log(f"OPF file located: {opf_path}")
    
    # Parse OPF
    opf_tree = ET.parse(opf_path)
    opf_root = opf_tree.getroot()
    
    manifest = opf_root.find(".//{http://www.idpf.org/2007/opf}manifest")
    spine = opf_root.find(".//{http://www.idpf.org/2007/opf}spine")
    if manifest is None or spine is None:
        log("Error: Manifest or Spine not found in OPF.")
        shutil.rmtree(temp_dir)
        sys.exit(1)
        
    manifest_items = {item.attrib.get("id"): item.attrib.get("href") for item in manifest if item.attrib.get("id")}
    
    # Identify spine items that are XHTML/HTML
    xhtml_items = []
    for itemref in spine:
        idref = itemref.attrib.get("idref")
        if idref in manifest_items:
            href = manifest_items[idref]
            if href.endswith((".xhtml", ".html", ".xml")):
                xhtml_items.append(href)
                
    log(f"Found {len(xhtml_items)} HTML/XHTML file(s) to process.")
    
    block_tags = [
        "{http://www.w3.org/1999/xhtml}p", "{http://www.w3.org/1999/xhtml}li",
        "{http://www.w3.org/1999/xhtml}h1", "{http://www.w3.org/1999/xhtml}h2",
        "{http://www.w3.org/1999/xhtml}h3", "{http://www.w3.org/1999/xhtml}h4",
        "{http://www.w3.org/1999/xhtml}h5", "{http://www.w3.org/1999/xhtml}h6",
        "{http://www.w3.org/1999/xhtml}blockquote", "{http://www.w3.org/1999/xhtml}td",
        "{http://www.w3.org/1999/xhtml}th",
        "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "td", "th"
    ]
    total_edited_blocks = 0
    total_cached_blocks = 0
    
    # Count total block elements to edit
    total_blocks = 0
    for item_href in xhtml_items:
        f_path = os.path.join(opf_dir, item_href)
        if os.path.exists(f_path):
            try:
                with open(f_path, "rb") as f:
                    r_bytes = f.read()
                sanitized_xml = sanitize_xhtml_for_xml_parser(r_bytes)
                h_root = ET.fromstring(sanitized_xml.encode('utf-8'))
                for el in h_root.iter():
                    if el.tag in block_tags:
                        text = el.text or ''
                        children_str = ''.join(ET.tostring(child, encoding='utf-8').decode('utf-8') for child in el)
                        inner_xml = text + children_str
                        if inner_xml.strip():
                            total_blocks += 1
            except Exception:
                pass
    log(f"Total block elements to edit across all files: {total_blocks}")
    
    completed_blocks_count = 0
    
    for item_idx, item_href in enumerate(xhtml_items):
        file_path = os.path.join(opf_dir, item_href)
        log(f"Editing file {item_idx+1}/{len(xhtml_items)}: {item_href}")
        
        if not os.path.exists(file_path):
            log(f"Warning: File {file_path} not found! Skipping.")
            continue
            
        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
                
            sanitized = sanitize_xhtml_for_xml_parser(raw_bytes)
            html_root = ET.fromstring(sanitized.encode('utf-8'))
            
            modified = False
            for el in html_root.iter():
                if el.tag in block_tags:
                    text = el.text or ''
                    children_str = ''.join(ET.tostring(child, encoding='utf-8').decode('utf-8') for child in el)
                    inner_xml = text + children_str
                    
                    if not inner_xml.strip():
                        continue
                        
                    completed_blocks_count += 1
                    try:
                        prog_path = os.path.join(paths["cache_dir"], "edit_progress.json")
                        with open(prog_path, "w", encoding="utf-8") as pf:
                            json.dump({
                                "current_file": item_idx + 1,
                                "total_files": len(xhtml_items),
                                "percent": round((completed_blocks_count / total_blocks) * 100.0, 1) if total_blocks > 0 else 0.0,
                                "completed_blocks": completed_blocks_count,
                                "total_blocks": total_blocks
                            }, pf)
                    except Exception:
                        pass
                        
                    h = get_hash(inner_xml)
                    if h in cache:
                        edited_inner_xml = cache[h]
                        total_cached_blocks += 1
                    else:
                        log(f"  Editing block ({len(inner_xml)} chars)...")
                        pm = PlaceholderManager()
                        protected = pm.protect(inner_xml)
                        
                        edited_protected = edit_segment_with_retry(protected, pm, args.api_url)
                        
                        if not edited_protected:
                            log("  Failed to edit block. Keeping original.")
                            edited_inner_xml = inner_xml
                        else:
                            edited_inner_xml = pm.restore(edited_protected)
                            
                        cache[h] = edited_inner_xml
                        total_edited_blocks += 1
                        
                        if total_edited_blocks % 5 == 0:
                            try:
                                with open(cache_path, "w", encoding="utf-8") as cf:
                                    json.dump(cache, cf, ensure_ascii=False, indent=2)
                            except Exception as e:
                                log(f"Warning: Failed to save cache: {e}")
                                
                    dummy_xml = f'<div xmlns="http://www.w3.org/1999/xhtml">{edited_inner_xml}</div>'
                    try:
                        sanitized_dummy = sanitize_xhtml_for_xml_parser(dummy_xml.encode('utf-8'))
                        dummy_root = ET.fromstring(sanitized_dummy.encode('utf-8'))
                        el.text = None
                        el.tail = None
                        for child in list(el):
                            el.remove(child)
                        el.text = dummy_root.text
                        for child in dummy_root:
                            el.append(child)
                        modified = True
                    except Exception as e:
                        log(f"  Warning: Failed to parse edited XML: {e}")
                        
            if modified:
                rough_string = ET.tostring(html_root, encoding='utf-8')
                with open(file_path, "wb") as f:
                    f.write(rough_string)
                    
        except Exception as e:
            log(f"Error processing file {item_href}: {e}")
            
    # Save final cache
    try:
        with open(cache_path, "w", encoding="utf-8") as cf:
            json.dump(cache, cf, ensure_ascii=False, indent=2)
        log(f"Saved final cache to {cache_path}. Total blocks edited: {total_edited_blocks}, Cached: {total_cached_blocks}")
    except Exception as e:
        log(f"Warning: Failed to save final cache: {e}")
        
    # Re-pack EPUB
    log(f"Re-packaging edited EPUB to: {args.output}")
    if os.path.exists(args.output):
        os.remove(args.output)
        
    try:
        with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED) as z:
            # mimetype must be first and uncompressed
            mimetype_path = os.path.join(temp_dir, "mimetype")
            if os.path.exists(mimetype_path):
                z.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)
            for root_d, dirs, files in os.walk(temp_dir):
                for file in files:
                    full_p = os.path.join(root_d, file)
                    rel_p = os.path.relpath(full_p, temp_dir)
                    if rel_p == "mimetype":
                        continue
                    z.write(full_p, rel_p)
        log("EPUB re-packaged successfully!")
    except Exception as e:
        log(f"Error: Failed to re-package EPUB: {e}")
    finally:
        shutil.rmtree(temp_dir)
        
    try:
        prog_path = os.path.join(paths["cache_dir"], "edit_progress.json")
        with open(prog_path, "w", encoding="utf-8") as pf:
            json.dump({
                "current_file": len(xhtml_items),
                "total_files": len(xhtml_items),
                "percent": 100.0
            }, pf)
    except Exception:
        pass
        
    log("=== EPUB EDITING PIPELINE FULLY COMPLETED ===")

if __name__ == "__main__":
    main()
