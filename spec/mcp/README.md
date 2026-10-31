# Pinned MCP wire fixture

`2026-07-28.schema.json` is the unmodified upstream protocol schema obtained from
[the official schema](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2026-07-28/schema.json).
`LICENSE` preserves the upstream license and attribution. Tests use only local
references and do not retrieve remote schemas. The fixture hash is frozen in
`ci/mcp-acceptance.json`; changing it requires reviewing the protocol profile.

The official Python SDK legacy client is separately pinned to `mcp==1.26.0` and
protocol `2025-11-25`. It is not evidence that the SDK implements the modern
metadata lifecycle. See [MCP automation](../../docs/mcp.md).
