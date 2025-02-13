import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Union


@dataclass
class Label:
    name: str = field(metadata={"transform": str.lower})
    required: bool = False
    data_type: str = "text"
    requires: List[str] = field(default_factory=list)
    required_with: List[str] = field(default_factory=list)
    is_json: bool = False


class Parser:
    """
    A flexible text parser that extracts labeled sections from text input.

    The parser identifies sections by looking for labels followed by separators
    (colon, tilde, or dash) and captures the content that follows. Labels are
    case-insensitive and can contain multiple words.

    Basic usage:
    ```python
    # Create parser with simple string labels
    parser = Parser(['name', 'description', 'requirements'])

    # Or use Label objects for more control
    parser = Parser([
        Label(name='name', required=True),
        Label(name='description', data_type='text'),
        Label(name='config', is_json=True)
    ])

    # Parse text
    result = parser.parse('''
        Name: John Smith
        Description: A software engineer
        Config: {"level": "senior"}
    ''')
    ```

    Features:
    - Case-insensitive label matching
    - Multiple separator support (`:`, `~`, `-`)
    - Multi-line content capture
    - Required field validation
    - JSON field parsing
    - Dependency validation between fields
    - Flexible label definitions with metadata

    Args:
        labels (List[Union[str, Label]]): List of labels to parse for. Can be
            simple strings or Label objects for more control. Label objects
            support additional features like required fields, JSON parsing,
            and field dependencies.

    Returns:
        Dict containing:
            - data: Dictionary of parsed values keyed by label name
            - errors: List of validation errors if any occurred
    """

    def __init__(self, labels: List[Union[str, Label]]):
        for index, label in enumerate(labels):
            if isinstance(label, str):
                labels[index] = Label(name=label.lower())

        # Sort labels by descending length to prevent partial matches
        self.__labels = sorted(labels, key=lambda x: -len(x.name))
        # Store lowercase keys in label map
        self.__label_map = {
            label.name.lower(): label for label in self.__labels
        }
        self.__patterns = self._build_patterns()

    def _build_patterns(self):
        patterns = []
        for label in self.__labels:
            # Replace spaces in label names with \s+ to allow multiple spaces
            label_regex = r"\s+".join(map(re.escape, label.name.split(" ")))
            # Require at least one colon/tilde/dash before treating it as a label
            pattern = re.compile(
                r"^\s*" + label_regex + r"\s*[:~\-]+\s*",
                re.IGNORECASE,
            )
            patterns.append((label.name, pattern))
        return patterns

    def parse(self, text: str) -> Dict:
        """
        Parses the text into a structure of lists (one list per label).
        This original parse method lumps together values for each label into arrays.
        """
        text = self._clean_text(text)
        lines = [line.rstrip() for line in text.split("\n")]

        raw_data = {label.name: [] for label in self.__labels}
        current_label = None
        current_entry = ""

        for line in lines:
            label_name, value = self._parse_line(line)

            if label_name:
                if current_label:
                    self._finalize_entry(raw_data, current_label, current_entry)
                current_label = label_name
                current_entry = value
            else:
                if current_label:
                    # Append the line to the current entry, ensuring we handle new lines correctly
                    current_entry += (
                        "\n" + line.strip() if current_entry else line.strip()
                    )

        if current_label:
            self._finalize_entry(raw_data, current_label, current_entry)

        return self._process_results(raw_data)

    def parse_blocks(self, text: str, block_label: str) -> List[Dict]:
        """
        Parses the text into multiple blocks. Each block starts whenever the specified
        'block_label' is encountered. The label definitions and validations still apply,
        but the result is now a list of dictionaries (one per block).

        Example:
            blocks = parser.parse_blocks(text, 'resource')
            # => [
            #     {"resource": "...", "reason": "...", "recommended": "..."},
            #     {"resource": "...", "reason": "...", "recommended": "..."},
            #     ...
            # ]

        Args:
            text (str): The text to parse.
            block_label (str): The label that signifies the start of a new block.

        Returns:
            List[Dict]: A list of parsed blocks, where each block is
                        a dict of label -> list-of-values or single value
        """
        text = self._clean_text(text)
        lines = [line.rstrip() for line in text.split("\n")]
        block_label_lower = block_label.lower()

        blocks = []
        raw_data = {label.name: [] for label in self.__labels}
        current_label = None
        current_entry = ""
        have_any_data = False

        for line in lines:
            label_name, value = self._parse_line(line)

            if label_name:
                # (1) First finalize the previous label for the "old" block
                if current_label is not None:
                    self._finalize_entry(raw_data, current_label, current_entry)

                # (2) If it's a new block label and we already have data, finalize the old block
                if label_name.lower() == block_label_lower and have_any_data:
                    # Debug: see raw_data for the old block
                    blocks.append(self._process_results(raw_data))
                    raw_data = {label.name: [] for label in self.__labels}

                # (3) Now set up the new label
                current_label = label_name
                current_entry = value
                have_any_data = True
            else:
                # no label => treat as continuation
                if current_label:
                    current_entry += (
                        "\n" + line.strip() if current_entry else line.strip()
                    )

        # end of loop: finalize the last label in the last block
        if current_label:
            self._finalize_entry(raw_data, current_label, current_entry)
        if have_any_data:
            blocks.append(self._process_results(raw_data))

        return blocks

    def _clean_text(self, text):
        # First, handle any code blocks
        def extract_content(match):
            return match.group(1)  # Just return the content inside

        # Handle all code blocks, regardless of language
        text = re.sub(
            r"```(?:\w+)?\s*(.*?)\s*```", extract_content, text, flags=re.DOTALL
        )

        # Remove inline code markers
        text = re.sub(r"`([^`]+)`", r"\1", text)

        # # Remove leading non-word characters (but preserve colons)
        # text = re.sub(r"^\s*([^:\w]*)\b", "", text, flags=re.MULTILINE)

        return text.strip()

    def _parse_line(self, line):
        # 1) Try pattern list
        for label_name, pattern in self.__patterns:
            if match := pattern.match(line):
                value_start = match.end()
                value = line[value_start:].strip()
                return label_name, value

        # 2) Fallback
        for label_name in self.__label_map:
            if line.strip().lower().startswith(label_name.lower()):
                remain = line.strip()[len(label_name) :]
                if re.match(r"^\s*[:~\-]+", remain):
                    # returns label
                    content = re.sub(r"^\s*[:~\-]+", "", remain).strip()
                    return label_name, content
                else:
                    # treat as continuation
                    return None, line.strip()

        # No match; treat as continuation
        return None, None

    def _finalize_entry(self, data, label_name, entry):
        if entry is None:
            entry = ""
        content = entry.strip()

        if content:
            if label_name not in data:
                data[label_name] = []
            data[label_name].append(content)

    def _process_results(self, raw_data):
        processed = {}
        errors = []

        for label_name in raw_data:
            label_def = self.__label_map[label_name.lower()]
            # Ensure label name is lowercase in output
            processed[label_name.lower()] = []

            for entry in raw_data[label_name]:
                processed_entry, error = self._process_entry(label_def, entry)
                processed[label_name.lower()].append(processed_entry)
                if error:
                    errors.append(error)

        errors += self._validate_dependencies(processed)
        return {"data": processed, "errors": errors}

    def _process_entry(self, label_def, entry):
        if label_def.is_json:
            try:
                return json.loads(entry), None
            except json.JSONDecodeError as e:
                return entry, f"JSON error in '{label_def.name}': {str(e)}"
        return entry, None

    def _validate_dependencies(self, data):
        errors = []
        for label_name, entries in data.items():
            # Use lowercase key to look up label definition
            label_def = self.__label_map[label_name.lower()]

            if label_def.required and not entries:
                errors.append(f"Required label '{label_name}' missing")

            if entries:
                for req in label_def.required_with:
                    # Use lowercase when checking required dependencies
                    if not data.get(req.lower(), []):
                        errors.append(f"'{label_name}' requires '{req}'")
        return errors
