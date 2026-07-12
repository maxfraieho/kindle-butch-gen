import hashlib
import re

def get_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def split_into_segments(text, max_chars=1200):
    paragraphs = text.split("\n\n")
    segments = []
    current_segment = []
    current_length = 0
    
    for p in paragraphs:
        p_len = len(p)
        if p_len > max_chars:
            if current_segment:
                segments.append("\n\n".join(current_segment))
                current_segment = []
                current_length = 0
            # Split large paragraph by sentences
            sentences = re.split(r'(?<=[.!?])\s+', p)
            curr_sent_group = []
            curr_sent_len = 0
            for s in sentences:
                if curr_sent_len + len(s) > max_chars:
                    if curr_sent_group:
                        segments.append(" ".join(curr_sent_group))
                    curr_sent_group = [s]
                    curr_sent_len = len(s)
                else:
                    curr_sent_group.append(s)
                    curr_sent_len += len(s) + 1
            if curr_sent_group:
                segments.append(" ".join(curr_sent_group))
        else:
            if current_length + p_len > max_chars:
                segments.append("\n\n".join(current_segment))
                current_segment = [p]
                current_length = p_len
            else:
                current_segment.append(p)
                current_length += p_len + 2
                
    if current_segment:
        segments.append("\n\n".join(current_segment))
        
    return segments

def to_xml_format(text):
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
