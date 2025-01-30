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
        for label_name, pattern in self.__patterns:
            if match := pattern.match(line):
                # Check to see if this is indeed a seperator
                # or if it is a continuation of the previous label
                value_start = match.end()
                value = line[value_start:].strip()
                return label_name, value

        # Check if the line starts with a label name but is not a valid entry
        for label_name in self.__label_map:
            if line.strip().startswith(label_name):
                # Check if the line has a valid separator
                if not re.search(r"[:~\-]", line):
                    return (
                        None,
                        line.strip(),
                    )  # Treat as continuation, return the line

                # Return label and value
                return (
                    label_name,
                    line[len(label_name) :].strip(),
                )

        return None, None

    def _finalize_entry(self, data, label_name, entry):
        if entry is None:
            entry = ""
        content = entry.strip()
        # label_def = self.__label_map[label_name.lower()]

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
