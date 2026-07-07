import re

class PlaceholderManager:
    def __init__(self):
        self.placeholders = {}
        self.counter = 0

    def add(self, text, prefix):
        key = f"__{prefix}_{self.counter}__"
        self.placeholders[key] = text
        self.counter += 1
        return key

    def protect(self, text):
        if not text:
            return ""
            
        # 0. Standalone image lines — protect the ENTIRE line, not just the URL,
        # so the LLM never sees markdown image syntax at all
        def image_line_repl(match):
            return self.add(match.group(0), "IMAGE_LINE")
        text = re.sub(r"^!\[[^\]]*\]\([^)]+\)\s*$", image_line_repl, text, flags=re.MULTILINE)

        # 1. Code blocks
        def cb_repl(match):
            return self.add(match.group(0), "CODE_BLOCK")
        text = re.sub(r"```[\s\S]*?```", cb_repl, text)

        # 2. LaTeX blocks
        def math_block_repl(match):
            return self.add(match.group(0), "MATH_BLOCK")
        text = re.sub(r"\$\$[\s\S]*?\$\$", math_block_repl, text)

        # 3. LaTeX inline
        def math_inline_repl(match):
            return self.add(match.group(0), "MATH_INLINE")
        text = re.sub(r"\$[^\$\n]+?\$", math_inline_repl, text)

        # 4. Inline code
        def inline_code_repl(match):
            return self.add(match.group(0), "INLINE_CODE")
        text = re.sub(r"`[^`\n]+?`", inline_code_repl, text)

        # 5. Markdown link/image URLs or HTML link targets
        def link_url_repl(match):
            prefix = match.group(1)
            url = match.group(2)
            suffix = match.group(3)
            placeholder = self.add(url, "LINK_URL")
            return f"{prefix}{placeholder}{suffix}"
        text = re.sub(r"(\]\s*\()([^\s()]+(?:\([^\s()]+\)[^\s()]*)*)(\))", link_url_repl, text)

        # 6. Raw URLs
        def raw_url_repl(match):
            return self.add(match.group(0), "RAW_URL")
        text = re.sub(r"https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'*+,;=%]+", raw_url_repl, text)

        # 7. HTML/XML tags
        def html_tag_repl(match):
            return self.add(match.group(0), "HTML_TAG")
        text = re.sub(r"<[a-zA-Z/!][^>]*?>", html_tag_repl, text)

        return text

    def normalize_placeholders(self, text):
        if not text:
            return ""
        prefixes = set()
        for key in self.placeholders.keys():
            match = re.match(r"^__([A-Z_]+?)_[0-9]+__$", key)
            if match:
                prefixes.add(match.group(1))
        
        for prefix in prefixes:
            flat_prefix = prefix.replace("_", "")
            pattern = re.compile(
                r'__(?:' + '|'.join([re.escape(prefix), re.escape(flat_prefix)]) + r')[-_\s]*(\d+)\s*__',
                re.IGNORECASE
            )
            text = pattern.sub(rf'__{prefix}_\1__', text)
        return text

    def restore(self, text):
        if not text:
            return ""
        text = self.normalize_placeholders(text)
        keys = list(self.placeholders.keys())
        keys.reverse()
        for key in keys:
            text = text.replace(key, self.placeholders[key])
        return text

    @staticmethod
    def strip_formatting(text):
        """Used for TTS: strips all Markdown and HTML formatting tags."""
        if not text:
            return ""
        text = re.sub(r"```[\s\S]*?```", "", text) # Remove code blocks
        text = re.sub(r"`[^`\n]+?`", "", text)     # Remove inline code
        text = re.sub(r"<[^>]+>", "", text)         # Remove HTML tags
        text = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", "", text) # Images
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text) # Keep link text, strip URLs
        text = re.sub(r"\$\$[\s\S]*?\$\$", "", text) # Remove LaTeX math blocks
        text = re.sub(r"\$(?!\s)[^\$\n]+?(?<!\s)\$", "", text) # Restrict LaTeX inline
        text = re.sub(r"^\s*#+\s+", "", text, flags=re.MULTILINE) # Headers
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE) # Bullet points
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE) # Numbered lists
        
        # Paired Markdown formatting removal (preserves snake_case words like some_variable_name)
        text = re.sub(r"\*\*(?=\S)([^\*]+?)(?<=\S)\*\*", r"\1", text)
        text = re.sub(r"__(?=\S)([^_]+?)(?<=\S)__", r"\1", text)
        text = re.sub(r"(?<!\w)\*(?=\S)([^\*]+?)(?<=\S)\*(?!\w)", r"\1", text)
        text = re.sub(r"(?<!\w)_(?=\S)([^_]+?)(?<=\S)_(?!\w)", r"\1", text)
        text = re.sub(r"~~(?=\S)([^~]+?)(?<=\S)~~", r"\1", text)
        
        # Stray placeholders (MUST be done after paired formatting removal)
        text = re.sub(r"__[A-Z0-9_]+__", "", text)
        return text
