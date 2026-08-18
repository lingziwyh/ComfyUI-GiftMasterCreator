# Security Policy

## Supported versions

Security fixes are provided for the latest release and the current `main`
branch. Older releases may require an upgrade before a fix can be applied.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting feature for this
repository. Do not include credentials, private images, full workflow files,
or working exploit details in a public issue.

If private reporting is unavailable, open a public issue that asks the
maintainer for a private contact channel without disclosing sensitive details.

Include the affected version, ComfyUI version, operating system, minimal
reproduction steps, and expected impact. Replace all API keys, endpoint tokens,
personal data, and private media with harmless placeholders.

## API key handling

- Prefer a dedicated environment variable whose name starts with
  `GIFTMASTER_`. Bind it to the intended API origin through the companion
  `<VARIABLE_NAME>_ORIGIN` environment variable. This keeps the credential
  outside the workflow and prevents an imported workflow from redirecting it
  to another host.
- GiftMasterCreator intentionally does not expose a direct-key widget. A
  password-looking ComfyUI widget can still serialize plaintext into workflow
  and browser state, so environment credentials are required for authenticated
  requests.
- Trusted companion extensions may use the versioned, runtime-only credential
  slot interface. A slot is bound to one exact API configuration and stores no
  key on disk, but it is a process-wide capability. Use it only when ComfyUI is
  bound exclusively to loopback on a single-user workstation; never expose
  such a session through a LAN listener, permissive CORS, or reverse proxy.
- Never commit or share a workflow containing a real key. Revoke and rotate a
  key immediately if it may have been exposed.
- Use a dedicated, least-privilege key with provider-side spending limits when
  the provider supports them.
- Use HTTPS endpoints you trust. Do not point the node at an unknown proxy or
  a service whose data-retention policy you have not reviewed.
- Automatic retries are deliberately conservative. Timeouts, HTTP 408, and
  server-side 5xx responses are not replayed because the first request may
  already have incurred work or cost.

GiftMasterCreator does not require a bundled provider credential. It is
designed for user-configured API services and does not include private or
internal provider endpoints, deployment identifiers, or secrets.

## Data sent to the configured API

Running an API Skill request sends the data needed for that request to the API
endpoint selected by the user. Depending on the workflow, this can include:

- task text and gift requirements;
- the selected Skill instructions and supporting reference text;
- connected images and their encoded contents;
- generation settings and conversation messages required by the API protocol.

Do not submit confidential, personal, biometric, copyrighted, or regulated
material unless you are authorized to do so and the chosen provider's terms,
retention policy, and processing region are acceptable. GiftMasterCreator
cannot control how a third-party endpoint stores or processes submitted data.

## Safe publication checklist

Before publishing a workflow, issue, log, or screenshot:

1. Remove direct API keys and authorization headers.
2. Replace private endpoints and account-specific deployment identifiers.
3. Remove personal or confidential images and prompt content.
4. Inspect workflow JSON and ComfyUI prompt history for serialized widget
   values.
5. Confirm that no official MiniMax H3 Skill text, prompt guide, model file, or
   other third-party material has been copied into the report.
