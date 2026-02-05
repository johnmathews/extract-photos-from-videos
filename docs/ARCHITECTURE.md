# Architecture Documentation

This directory contains diagrams documenting the `epm` code flow.

## Diagrams

| Diagram | Description |
|---------|-------------|
| [EPM Control Flow](epm-control-flow.md) | Main decision tree from invocation to completion |
| [EPM Sequence](epm-sequence.md) | Local ↔ remote interaction and tmux resilience model |
| [Python Pipeline](python-pipeline.md) | Three-phase extraction process detail |

## Rendering

These diagrams use Mermaid syntax:
- **GitHub**: Renders natively in `.md` files
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **CLI**: `npm install -g @mermaid-js/mermaid-cli` then `mmdc -i file.md -o file.svg`
- **Online**: Paste into https://mermaid.live
