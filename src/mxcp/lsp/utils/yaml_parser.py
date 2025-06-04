from yaml import load, CLoader as Loader
import yaml
from typing import Optional, Tuple
from .models import Parameter
from lsprotocol import types


class YamlParser:
    def __init__(self, yaml_string: str):
        self.yaml_object = load(yaml_string, Loader=Loader)
        self.code = self.__get_code()
        self.code_span = self.__get_code_span(yaml_string)

    def get_parameters(self) -> Optional[list[Parameter]]:
        """Get the parameters from the YAML object."""
        if (
            self.yaml_object is not None
            and "tool" in self.yaml_object
            and "parameters" in self.yaml_object["tool"]
        ):
            parameters = self.yaml_object["tool"]["parameters"]
            return [
                Parameter(
                    param["name"], param["type"], param["description"], param["default"]
                )
                for param in parameters
            ]
        return None

    def should_provide_lsp(
        self, cursor_position: Optional[types.Position] = None
    ) -> bool:
        """Check if LSP should be provided for this YAML document."""
        return (
            self._is_valid_mxcp_structure()
            and self._has_inline_sql_code()
            and self._cursor_in_code_range(cursor_position)
        )

    def _is_valid_mxcp_structure(self) -> bool:
        """Check if the YAML has the basic MXCP tool structure."""
        return (
            self.yaml_object is not None
            and "mxcp" in self.yaml_object
            and "tool" in self.yaml_object
            and "source" in self.yaml_object["tool"]
            and "code" in self.yaml_object["tool"]["source"]
        )

    def _has_inline_sql_code(self) -> bool:
        """Check if the code is inline SQL (not a .sql file reference)."""
        if not self._is_valid_mxcp_structure():
            return False
        
        code = self.yaml_object["tool"]["source"]["code"]
        return (
            isinstance(code, str)
            and not code.strip().lower().endswith(".sql")
        )

    def _cursor_in_code_range(self, cursor_position: Optional[types.Position]) -> bool:
        """Check if the cursor position is within the code block range."""
        if cursor_position is None:
            return True
        
        if self.code_span is None:
            return False
        
        return (
            self.code_span[0].line - 1 <= cursor_position.line <= self.code_span[1].line + 1
        )

    def __get_code(self):
        """Get the code from the YAML object."""
        if not self._has_inline_sql_code():
            return None
        return self.yaml_object["tool"]["source"]["code"]

    def __get_code_span(
        self, yaml_text: str
    ) -> Optional[Tuple[types.Position, types.Position]]:
        """
        Return (start_line0, start_col0, end_line0, end_col0) - all zero-based -
        for the scalar that is the value of the key `code:`.

        The columns are counted *after* indentation on their respective lines.
        Returns None if no `code:` key exists.
        """
        root = yaml.compose(yaml_text)  # keeps start/end marks
        if root is None:
            return None

        # --- 1. find the ScalarNode that is the value of the key `code`
        def find(node):
            if isinstance(node, yaml.MappingNode):
                for k, v in node.value:
                    if k.value == "code":
                        return v
                    hit = find(v)
                    if hit:
                        return hit
            elif isinstance(node, yaml.SequenceNode):
                for child in node.value:
                    hit = find(child)
                    if hit:
                        return hit

        node = find(root)
        if node is None:
            return None  # no `code:` at all

        txt = yaml_text

        # --- 2. byte offset of the first *content* character
        p_start = node.start_mark.pointer
        if node.style in ("|", ">"):  # block scalar
            p_start = txt.find("\n", p_start) + 1  # jump to next line
            while txt[p_start] in " \t":  # skip indent
                p_start += 1
        elif node.style in ("'", '"'):  # quoted inline
            p_start += 1  # skip opening quote
        # plain inline: already on the first byte

        # --- 3. byte offset of the last *content* character
        if node.style in ("|", ">"):  # block scalar
            p_end = node.end_mark.pointer - 1  # step back from final newline
        elif node.style in ("'", '"'):  # quoted inline
            p_end = node.end_mark.pointer - 2  # before closing quote
        else:  # plain inline
            p_end = node.end_mark.pointer - 1
        # drop trailing spaces / tabs / new-lines
        # while txt[p_end] in " \t\r\n":
        #     p_end -= 1

        # --- 4. translate byte offsets → (line0, col0)
        def to_line_col(ptr: int):
            line0 = txt.count("\n", 0, ptr)
            after_last_nl = txt.rfind("\n", 0, ptr) + 1
            col0 = ptr - after_last_nl  # indent is not counted
            return line0, col0

        start_line0, start_col0 = to_line_col(p_start)
        end_line0, end_col0 = to_line_col(p_end)

        return (
            types.Position(start_line0, start_col0),
            types.Position(end_line0, end_col0),
        ) 