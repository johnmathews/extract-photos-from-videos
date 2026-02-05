# EPM Code Flow Diagrams

## Flowchart (Main Control Flow)

```mermaid
flowchart TD
    A[epm invoked] --> B[Parse arguments]
    B --> C{Video path provided?}
    C -->|No| D[Check stdin]
    D --> E{Input from pipe?}
    E -->|Yes| F[Read VIDEO from stdin]
    E -->|No| G[Error: input_file required]
    C -->|Yes| H[Map host label to SSH host]
    F --> H

    H --> I{Existing tmux session?}
    I -->|Yes| J[Reattach to session]
    J --> K[Read result & log]
    K --> L[Exit]

    I -->|No| M[Auto-setup on remote]
    M --> N{Repo exists?}
    N -->|No| O[Clone repo + uv sync]
    N -->|Yes| P[git pull + uv sync]
    O --> Q[Upload extraction script]
    P --> Q

    Q --> R[Start tmux session]
    R --> S[Attach to session]

    subgraph Remote["Remote Execution (in tmux)"]
        T[Validate video exists] --> U[Compute output subdir name]
        U --> V{Output already exists?}
        V -->|Yes| W{Skip or overwrite?}
        W -->|Skip| X[Write result: skipped]
        W -->|Overwrite| Y[Create temp dir]
        V -->|No| Y

        Y --> Z[Symlink video to temp dir]
        Z --> AA[Run extract_photos.main]

        subgraph Python["Python Pipeline"]
            AA --> BB[batch_processor.py]
            BB --> CC[extract.py]
            CC --> DD[1. Transcode to 320px]
            DD --> EE[2. Scan for photo frames]
            EE --> FF[3. Extract full-res frames]
            FF --> GG[borders.py: trim & add border]
        end

        GG --> HH[Copy photos to output]
        HH --> II[transcode_playback.py]
        II --> JJ{Immich enabled?}
        JJ -->|Yes| KK[immich.py: scan, album, share]
        JJ -->|No| LL[Skip Immich]
        KK --> MM[Write result file]
        LL --> MM
    end

    S --> MM
    MM --> NN[Copy console log]
    NN --> OO[Read remote result]
    OO --> PP[Log outcome locally]
    PP --> QQ[Done]
```

## Sequence Diagram (Local ↔ Remote Interaction)

```mermaid
sequenceDiagram
    participant User
    participant epm as epm (local)
    participant SSH
    participant Remote as Remote Host
    participant tmux
    participant Python as Python Pipeline

    User->>epm: epm "/path/to/video.mp4"
    epm->>epm: Parse args, map host

    epm->>SSH: Check for existing tmux session

    alt Session exists
        SSH-->>epm: Session found
        epm->>SSH: tmux attach-session
        SSH-->>User: Reattach to running extraction
    else No session
        epm->>SSH: Auto-setup (clone/pull, uv sync)
        SSH-->>epm: Setup complete

        epm->>SSH: Upload extraction script
        epm->>SSH: tmux new-session
        SSH->>tmux: Start session
        tmux->>Remote: Run extraction script

        epm->>SSH: tmux attach-session

        Remote->>Python: python -m extract_photos.main
        Python->>Python: Transcode (320px)
        Python->>Python: Scan for photos
        Python->>Python: Extract full-res frames
        Python-->>Remote: Photos extracted

        Remote->>Remote: Copy to output dir
        Remote->>Remote: Transcode video for playback

        opt Immich enabled
            Remote->>Remote: python -m extract_photos.immich
        end

        Remote->>Remote: Write result file
        tmux-->>SSH: Session ends
        SSH-->>epm: Connection closes

        epm->>SSH: Read result file
        SSH-->>epm: exit_code, photo_count, status
        epm->>epm: Log to ~/.epm/epm.log
    end

    epm-->>User: Done
```

## Python Pipeline Detail

```mermaid
flowchart LR
    subgraph main.py
        A[Parse CLI args]
    end

    subgraph batch_processor.py
        B[Find video files] --> C[For each video]
        C --> D[Check existing output]
        D --> E[Create output subdir]
    end

    subgraph extract.py
        F[transcode_lowres] --> G[scan_for_photos]
        G --> H[extract_fullres_frames]

        G --> G1[Step through frames]
        G1 --> G2[Detect uniform borders]
        G2 --> G3[Reject near-uniform]
        G3 --> G4[Perceptual hash dedup]
        G4 --> G5[Collect timestamps]

        H --> H1[Seek to timestamp]
        H1 --> H2[Validate frame]
        H2 --> H3[trim_and_add_border]
        H3 --> H4[Save JPEG]
    end

    A --> B
    E --> F
    H4 --> I[Return photo count]
```

## Notes

These diagrams use Mermaid syntax. To render them:
- **GitHub**: Paste into any `.md` file - GitHub renders Mermaid natively
- **VS Code**: Install "Markdown Preview Mermaid Support" extension
- **CLI**: Use `mmdc` (mermaid-cli): `npm install -g @mermaid-js/mermaid-cli`
- **Online**: Paste into https://mermaid.live

The flowchart shows the complete decision tree through `epm`. The sequence diagram emphasizes the local↔remote handoff and resilience model (tmux). The Python pipeline detail zooms into the three-phase extraction process.
