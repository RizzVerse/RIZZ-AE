# RIZZ AE

RIZZ AE is a starter cloud media-processing service controlled through Claude using the Model Context Protocol (MCP). It uses FastAPI and FFmpeg. This is a basic processing backend, not a full multi-track timeline editor.

## Features
- Mobile-friendly browser upload page
- Bearer-token protection for uploads, downloads, and MCP
- MCP tools: status, media info, trim, resize, audio extraction, text overlay, audio normalization, speed change, and thumbnail creation
- FFmpeg installed in the Docker image
- Railway-ready Docker configuration

## Deploy on Railway
1. Create a Railway project and deploy this GitHub repository.
2. Add a persistent volume mounted at `/data`.
3. Add environment variables:
   - `RIZZ_AE_ACCESS_TOKEN`: a long random secret; keep it private.
   - `RIZZ_AE_DATA_DIR`: `/data`
   - `RIZZ_AE_MAX_UPLOAD_MB`: `2048` or your chosen upload limit.
4. Generate a public HTTPS domain. Health check: `/health`.
5. MCP endpoint: `https://YOUR-DOMAIN/mcp`.

## Use
Open the service root URL, enter the bearer token, and upload a media file. The page returns a file ID. Configure a compatible MCP client to connect to the endpoint with bearer-token authentication. Export files are stored on the server and can be downloaded from `/download/EXPORT_FILE_ID` with the same bearer token.

## Security
- Never commit your access token or put it in this repository.
- Use HTTPS only.
- Set upload limits, storage quotas, backups, cleanup, and rate limits before public production use.
- Files are not automatically deleted; the persistent volume can fill up.
- Confirm that your Claude client supports remote Streamable HTTP MCP with bearer-token authentication. If it only supports OAuth, an OAuth-compatible setup is required.

## Current limitations
This project performs single-file FFmpeg operations. It does not yet provide a visual multi-track timeline, beat-sync editing, automatic subtitles, AI scene selection, or a full professional editing interface. Cloud deployment and Claude-client compatibility must be tested after deployment.
