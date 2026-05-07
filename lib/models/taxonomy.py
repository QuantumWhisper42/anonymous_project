from pydantic import BaseModel, Field

from lib.types import Language


class LabelTreeNode(BaseModel):
    title: str = Field(description="Label name")
    notes: str = Field(default="", description="Label notes")
    children: list["LabelTreeNode"] = Field(
        default_factory=list, description="Sub labels"
    )


def build_label_tree_node_path_from_str(
    label_tree_node_path_str: list[str],
    taxonomy_roots: list[LabelTreeNode],
) -> list[LabelTreeNode]:
    result = []

    current_taxonomy_roots = taxonomy_roots

    for title in label_tree_node_path_str:
        for node in current_taxonomy_roots:
            if node.title == title:
                new_node = LabelTreeNode(
                    title=node.title,
                    notes=node.notes,
                    children=[],
                )
                result.append(new_node)
                current_taxonomy_roots = node.children
                break
        else:
            print(title, label_tree_node_path_str)
            raise ValueError("Cannot build label_tree_node_path from str")
    return result


def extract_paths(node: LabelTreeNode) -> list[list[LabelTreeNode]]:
    if not node.children:
        return [[node]]

    paths = []
    for child in node.children:
        for sub_path in extract_paths(child):
            paths.append([node] + sub_path)
    return paths


def parse_label_trees_from_json(data: dict, language: Language) -> LabelTreeNode:
    return LabelTreeNode(
        title=data[f"title_{language}"],
        notes=data.get(f"notes_{language}", ""),
        children=[
            parse_label_trees_from_json(child, language)
            for child in data.get("children", [])
        ],
    )
