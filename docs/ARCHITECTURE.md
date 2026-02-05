# Architecture Documentation

This directory contains diagrams documenting the `epm` code flow.

## Flow Diagrams

| Diagram | Description |
|---------|-------------|
| [EPM Control Flow](epm-control-flow.md) | Main decision tree from invocation to completion |
| [EPM Sequence](epm-sequence.md) | Local ↔ remote interaction and tmux resilience model |
| [Python Pipeline](python-pipeline.md) | Three-phase extraction process detail |

## Call Graphs

Three approaches for visualizing function/method calls:

| Approach | Description | Pros | Cons |
|----------|-------------|------|------|
| [Manual (Mermaid)](callgraph-manual/README.md) | Hand-crafted call graph | Clean, readable, shows key relationships | Requires manual updates |
| [AST Analysis](callgraph-pyan/README.md) | Auto-generated via Python AST | Automatic, complete | Can be noisy |
| [pyreverse (UML)](callgraph-pyreverse/README.md) | Module dependencies via pylint | Standard UML, automatic | Module-level only |

## Rendering

**Mermaid diagrams** (flow diagrams, manual call graph):
- **GitHub**: Renders natively in `.md` files
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **CLI**: `npm install -g @mermaid-js/mermaid-cli` then `mmdc -i file.md -o file.svg`
- **Online**: Paste into https://mermaid.live

**Graphviz diagrams** (auto-generated call graphs):
- **CLI**: `dot -Tsvg input.dot -o output.svg`
- **Online**: Paste into https://dreampuf.github.io/GraphvizOnline
