# Live Dashboard

The dashboard is a read-only monitor for a campaign directory. It shows task progress, native receipts, camera frames, public decision records, and isolated infrastructure failures. It does not launch, stop, replay, or edit an evaluation.

```bash
./UI/run-dev.sh /path/to/campaign
```

The default address is `http://127.0.0.1:8766`. Use another port when needed:

```bash
PORT=8767 ./UI/run-dev.sh /path/to/campaign
```

For a remote cluster, forward the port from the cluster to your workstation:

```bash
ssh -N -L 8766:127.0.0.1:8766 <cluster-host>
```

Then open `http://127.0.0.1:8766` locally. Serve only a sanitized evidence directory. Do not point the monitor at a directory containing credentials, provider transcripts, raw RPC payloads, or private cluster metadata.
