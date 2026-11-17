"""Curated playbooks shipped with the playbooks V2 feature.

Every playbook is reference material: commands are rendered as text for the
operator to review and copy. The application never executes them.
"""

from __future__ import annotations

from redscribe.v2.playbooks.types import (
    ChecklistItem,
    Condition,
    ConditionOperator,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    StepKind,
    VariableDefinition,
    VariableKind,
)

_SCOPE = VariableDefinition(
    "scope",
    "Scope note",
    description="Written authorization and in-scope assets",
    required=True,
)
_WINDOW = VariableDefinition("window", "Test window", description="Agreed testing window")
_EVIDENCE = VariableDefinition("evidence_dir", "Evidence directory", default="evidence")
_TOOLSET = VariableDefinition(
    "toolset",
    "Tool profile",
    kind=VariableKind.CHOICE,
    choices=("standard", "conservative", "thorough"),
    default="standard",
)
_CASE = VariableDefinition("case_id", "Case id", description="Engagement or ticket identifier")
_FINDING = VariableDefinition("finding_id", "Finding id", description="Stable finding identifier")
_FLAG = VariableDefinition("flag", "Flag", description="Captured challenge flag")
_OPERATOR = VariableDefinition("operator", "Operator", description="Responsible examiner")


def _condition(field: str, operator: ConditionOperator, value: str = "") -> Condition:
    return Condition(field=field, operator=operator, value=value)


def _items(*specs: tuple[str, str, str, bool]) -> tuple[ChecklistItem, ...]:
    return tuple(
        ChecklistItem(
            id=item_id,
            label=label,
            detail=detail,
            required=required,
        )
        for item_id, label, detail, required in specs
    )


def _step(
    step_id: str,
    title: str,
    *,
    kind: StepKind = StepKind.ACTION,
    summary: str = "",
    command: str = "",
    snippet: str = "",
    depends_on: tuple[str, ...] = (),
    when: tuple[Condition, ...] = (),
    checklist: tuple[ChecklistItem, ...] = (),
    variables: tuple[str, ...] = (),
    minutes: int = 5,
    tags: tuple[str, ...] = (),
    note: str = "",
    optional: bool = False,
) -> PlaybookStep:
    return PlaybookStep(
        id=step_id,
        title=title,
        kind=kind,
        summary=summary,
        command_template=command,
        snippet_key=snippet,
        depends_on=depends_on,
        when=when,
        checklist=checklist,
        variables=variables,
        estimated_minutes=minutes,
        tags=tags,
        note=note,
        optional=optional,
    )


_WEB_STEPS = (
    _step(
        "confirm-scope",
        "Confirm authorization and scope",
        kind=StepKind.VERIFICATION,
        summary="Record the written scope before sending any request.",
        checklist=_items(
            (
                "scope-written",
                "Written scope is attached",
                "Verify dates, assets, and exclusions.",
                True,
            ),
            (
                "rules-ack",
                "Rules of engagement acknowledged",
                "Record the contact and stop conditions.",
                True,
            ),
        ),
        variables=("scope", "window"),
        minutes=5,
        tags=("admin", "scope"),
    ),
    _step(
        "inventory-web",
        "Inventory web assets",
        summary="Collect DNS names, base URLs, and technologies in scope.",
        command="echo '{{ target }}' | tee scope-targets.txt",
        snippet="subfinder",
        depends_on=("confirm-scope",),
        checklist=_items(
            ("hosts-listed", "Hosts enumerated", "Save a deduplicated host list.", True),
            ("urls-listed", "Base URLs recorded", "Include scheme and port.", False),
        ),
        minutes=10,
        tags=("recon", "web"),
    ),
    _step(
        "fingerprint",
        "Fingerprint services",
        summary="Identify server, framework, and TLS configuration.",
        snippet="http-headers",
        depends_on=("inventory-web",),
        command="curl -sSIL {{ url }}",
        checklist=_items(
            ("headers-saved", "Headers saved", "Store raw response headers.", True),
            ("tech-notes", "Technologies recorded", "Note framework and CDN hints.", False),
        ),
        minutes=8,
        tags=("recon", "web"),
    ),
    _step(
        "content-discovery",
        "Discover content",
        summary="Map visible directories and files with conservative settings.",
        snippet="ffuf-directories",
        depends_on=("fingerprint",),
        when=(_condition("toolset", ConditionOperator.EQ, "standard"),),
        command="ffuf -u {{ url }}/FUZZ -w wordlist.txt -mc 200,204,301,302,403",
        checklist=_items(
            (
                "wordlist-approved",
                "Wordlist approved",
                "Check the wordlist against scope rules.",
                True,
            ),
            ("results-saved", "Discovery output saved", "Export a sorted result set.", True),
        ),
        minutes=20,
        tags=("web", "content"),
        variables=("toolset",),
    ),
    _step(
        "auth-baseline",
        "Review authentication baseline",
        kind=StepKind.CHECKLIST,
        summary="Record session handling, password policy, and recovery flows.",
        depends_on=("fingerprint",),
        checklist=_items(
            (
                "session-flags",
                "Session cookie flags checked",
                "Check Secure, HttpOnly, and SameSite.",
                True,
            ),
            ("mfa-recorded", "MFA behavior recorded", "Note enrollment and recovery paths.", True),
            (
                "lockout-recorded",
                "Lockout behavior recorded",
                "Avoid account lockouts on live systems.",
                False,
            ),
        ),
        minutes=12,
        tags=("web", "auth"),
    ),
    _step(
        "structured-tests",
        "Run structured web tests",
        summary="Check injection, XSS, SSRF, and authorization boundaries.",
        depends_on=("auth-baseline", "content-discovery"),
        when=(_condition("toolset", ConditionOperator.NE, "conservative"),),
        checklist=_items(
            (
                "idor-checked",
                "Object-level authorization checked",
                "Compare two authorized identities.",
                True,
            ),
            (
                "injection-checked",
                "Injection surfaces checked",
                "Record payloads and responses.",
                True,
            ),
            (
                "upload-checked",
                "Upload handling checked",
                "Verify type and size enforcement.",
                False,
            ),
        ),
        minutes=35,
        tags=("web", "testing"),
        variables=("toolset",),
    ),
    _step(
        "consolidate",
        "Consolidate findings",
        kind=StepKind.VERIFICATION,
        summary="Deduplicate observations and link evidence to each finding.",
        depends_on=("structured-tests", "auth-baseline"),
        checklist=_items(
            (
                "findings-drafted",
                "Findings drafted",
                "Include impact and reproduction steps.",
                True,
            ),
            (
                "evidence-linked",
                "Evidence linked",
                "Attach requests, responses, and timestamps.",
                True,
            ),
            (
                "out-of-scope-reviewed",
                "Out-of-scope data removed",
                "Redact unrelated tenants and credentials.",
                True,
            ),
        ),
        minutes=15,
        tags=("reporting",),
    ),
)

_WEB_PLAYBOOK = Playbook(
    id=1,
    key="web-app-assessment",
    title="Web application assessment",
    description="A conservative web assessment workflow from scope confirmation to findings.",
    status=PlaybookStatus.ACTIVE,
    category="web",
    tags=("web", "http", "assessment"),
    version="1.2.0",
    steps=_WEB_STEPS,
    variables=(
        _SCOPE,
        _WINDOW,
        _TOOLSET,
        _EVIDENCE,
    ),
    owner="redscribe",
    created_at="2026-01-10T00:00:00+00:00",
    updated_at="2026-02-18T00:00:00+00:00",
    references=("OWASP ASVS", "OWASP Testing Guide"),
)

_HOST_STEPS = (
    _step(
        "host-scope",
        "Validate host scope",
        kind=StepKind.VERIFICATION,
        summary="Confirm the host identifier and maintenance constraints.",
        checklist=_items(
            ("host-confirmed", "Host confirmed", "Record IP, DNS name, and owner.", True),
            (
                "maintenance-checked",
                "Maintenance window checked",
                "Note any no-scan periods.",
                False,
            ),
        ),
        variables=("scope", "window"),
        minutes=5,
    ),
    _step(
        "host-ports",
        "Enumerate ports and services",
        snippet="nmap-quick-scan",
        depends_on=("host-scope",),
        command="nmap -sC -sV -oA {{ evidence_dir }}/nmap {{ target }}",
        checklist=_items(
            ("ports-saved", "Port scan saved", "Store raw nmap output.", True),
            ("services-labelled", "Services labelled", "Annotate unexpected services.", False),
        ),
        minutes=15,
        tags=("recon",),
        variables=("evidence_dir",),
    ),
    _step(
        "config-review",
        "Review host configuration",
        kind=StepKind.CHECKLIST,
        depends_on=("host-ports",),
        checklist=_items(
            ("patches-recorded", "Patch level recorded", "Capture OS and kernel version.", True),
            (
                "exposure-reviewed",
                "Network exposure reviewed",
                "Compare against the intended posture.",
                True,
            ),
            (
                "accounts-reviewed",
                "Local account policy reviewed",
                "Record password and lockout policy.",
                False,
            ),
        ),
        minutes=20,
    ),
    _step(
        "privilege-paths",
        "Document privilege paths",
        kind=StepKind.DECISION,
        depends_on=("config-review",),
        when=(_condition("user", ConditionOperator.EXISTS),),
        checklist=_items(
            (
                "sudo-reviewed",
                "Privilege commands reviewed",
                "Record only authorized findings.",
                True,
            ),
            ("path-notes", "Escalation notes written", "Describe preconditions and impact.", True),
        ),
        minutes=15,
        tags=("privesc",),
        variables=("user",),
    ),
    _step(
        "host-report",
        "Write host summary",
        kind=StepKind.VERIFICATION,
        depends_on=("privilege-paths",),
        checklist=_items(
            (
                "summary-written",
                "Summary written",
                "Include scope, methods, and constraints.",
                True,
            ),
            ("evidence-indexed", "Evidence indexed", "Link each artifact to a finding.", True),
        ),
        minutes=10,
    ),
)

_HOST_PLAYBOOK = Playbook(
    id=2,
    key="host-review",
    title="Host configuration review",
    description="Port, service, configuration, and privilege review for a single host.",
    status=PlaybookStatus.ACTIVE,
    category="host",
    tags=("host", "recon", "review"),
    version="1.1.0",
    steps=_HOST_STEPS,
    variables=(_SCOPE, _WINDOW, _EVIDENCE),
    created_at="2026-01-12T00:00:00+00:00",
    updated_at="2026-02-02T00:00:00+00:00",
)

_CTF_STEPS = (
    _step(
        "challenge-intake",
        "Challenge intake",
        kind=StepKind.NOTE,
        summary="Capture the statement, category, and download integrity.",
        checklist=_items(
            ("statement-saved", "Statement saved", "Quote the original prompt.", True),
            (
                "files-hashed",
                "Provided files hashed",
                "Record a checksum for each artifact.",
                False,
            ),
        ),
        minutes=3,
    ),
    _step(
        "binary-triage",
        "Triage the artifact",
        snippet="strings",
        depends_on=("challenge-intake",),
        command="file {{ target }}; strings -n 6 {{ target }} | head -80",
        checklist=_items(
            (
                "format-identified",
                "File format identified",
                "Note architecture, linker, and symbols.",
                True,
            ),
            (
                "strings-reviewed",
                "Strings reviewed",
                "Highlight prompts and suspicious paths.",
                False,
            ),
        ),
        minutes=8,
        tags=("ctf", "binary"),
    ),
    _step(
        "protection-review",
        "Record binary protections",
        kind=StepKind.VERIFICATION,
        depends_on=("binary-triage",),
        checklist=_items(
            (
                "protections-recorded",
                "Protections recorded",
                "Note NX, PIE, canary, and RELRO.",
                True,
            ),
            (
                "entrypoints-listed",
                "Entry points listed",
                "Identify main and interesting handlers.",
                False,
            ),
        ),
        minutes=7,
    ),
    _step(
        "hypothesis",
        "Write an exploitation hypothesis",
        kind=StepKind.DECISION,
        depends_on=("protection-review",),
        checklist=_items(
            ("hypothesis-written", "Hypothesis written", "State the expected bug class.", True),
            ("alternatives-listed", "Alternatives listed", "Keep a short fallback list.", False),
        ),
        minutes=10,
    ),
    _step(
        "solve-and-record",
        "Solve and record the flag",
        kind=StepKind.VERIFICATION,
        depends_on=("hypothesis",),
        checklist=_items(
            ("flag-captured", "Flag captured", "Paste the exact value.", True),
            ("writeup-drafted", "Writeup drafted", "Explain the path from bug to flag.", False),
        ),
        minutes=25,
        variables=("flag",),
    ),
)

_CTF_PLAYBOOK = Playbook(
    id=3,
    key="ctf-binary-triage",
    title="CTF binary triage",
    description="A repeatable triage path for binary exploitation challenges.",
    status=PlaybookStatus.ACTIVE,
    category="ctf",
    tags=("ctf", "binary", "triage"),
    version="1.0.0",
    steps=_CTF_STEPS,
    variables=(_CASE, _FLAG),
    created_at="2026-01-20T00:00:00+00:00",
    updated_at="2026-01-20T00:00:00+00:00",
)

_AD_STEPS = (
    _step(
        "ad-scope",
        "Record domain scope",
        kind=StepKind.VERIFICATION,
        checklist=_items(
            (
                "domain-confirmed",
                "Domain confirmed",
                "Record the DNS domain and DC addresses.",
                True,
            ),
            (
                "credentials-classified",
                "Credentials classified",
                "Mark authorization level for each account.",
                True,
            ),
        ),
        variables=("scope", "domain", "user"),
        minutes=6,
    ),
    _step(
        "ad-users",
        "Enumerate users and groups",
        snippet="kerbrute-user-enum",
        depends_on=("ad-scope",),
        command="kerbrute userenum -d {{ domain }} --dc {{ target }} users.txt",
        checklist=_items(
            ("users-recorded", "Accounts recorded", "Store names with discovery source.", True),
            ("groups-recorded", "Groups recorded", "Highlight privileged groups.", False),
        ),
        minutes=15,
        tags=("ad", "recon"),
    ),
    _step(
        "ad-shares",
        "Inspect accessible shares",
        snippet="smbclient-shares",
        depends_on=("ad-scope",),
        checklist=_items(
            ("shares-listed", "Shares listed", "Record access level per share.", True),
            (
                "sensitive-data-noted",
                "Sensitive data noted",
                "Do not copy secrets into notes.",
                False,
            ),
        ),
        minutes=12,
        tags=("ad", "smb"),
    ),
    _step(
        "ad-relationships",
        "Map identity relationships",
        kind=StepKind.DECISION,
        depends_on=("ad-users", "ad-shares"),
        checklist=_items(
            (
                "paths-recorded",
                "Attack paths recorded",
                "Describe preconditions and privileges.",
                True,
            ),
            (
                "false-positives-marked",
                "False positives marked",
                "Annotate uncertain links.",
                False,
            ),
        ),
        minutes=20,
        tags=("ad", "graph"),
    ),
    _step(
        "ad-evidence",
        "Package AD evidence",
        kind=StepKind.VERIFICATION,
        depends_on=("ad-relationships",),
        checklist=_items(
            ("outputs-exported", "Outputs exported", "Store command output with timestamps.", True),
            (
                "secrets-redacted",
                "Secrets redacted",
                "Remove passwords and tokens from exports.",
                True,
            ),
        ),
        minutes=10,
        variables=("evidence_dir",),
    ),
)

_AD_PLAYBOOK = Playbook(
    id=4,
    key="ad-recon",
    title="Active Directory reconnaissance",
    description="User, share, and relationship discovery for authorized AD assessments.",
    status=PlaybookStatus.ACTIVE,
    category="active-directory",
    tags=("ad", "recon", "identity"),
    version="1.3.0",
    steps=_AD_STEPS,
    variables=(_SCOPE, _EVIDENCE),
    created_at="2026-01-05T00:00:00+00:00",
    updated_at="2026-03-01T00:00:00+00:00",
)

_API_STEPS = (
    _step(
        "api-inventory",
        "Inventory API surface",
        summary="List documented and observed endpoints with methods and auth requirements.",
        checklist=_items(
            ("endpoints-listed", "Endpoints listed", "Include method, path, and auth.", True),
            ("spec-saved", "Specification saved", "Attach OpenAPI or discovery output.", False),
        ),
        minutes=10,
        tags=("api",),
    ),
    _step(
        "api-schema",
        "Review schemas and types",
        depends_on=("api-inventory",),
        checklist=_items(
            ("types-reviewed", "Types reviewed", "Note unexpected coercions.", True),
            (
                "rate-limits-recorded",
                "Rate limits recorded",
                "Record observed limits and headers.",
                False,
            ),
        ),
        minutes=10,
    ),
    _step(
        "api-authz",
        "Test authorization boundaries",
        kind=StepKind.VERIFICATION,
        depends_on=("api-schema",),
        when=(_condition("user", ConditionOperator.EXISTS),),
        checklist=_items(
            (
                "cross-identity-checked",
                "Cross-identity access checked",
                "Use two authorized identities.",
                True,
            ),
            (
                "object-ids-checked",
                "Object identifiers checked",
                "Verify tenant and record boundaries.",
                True,
            ),
        ),
        minutes=20,
        variables=("user",),
    ),
    _step(
        "api-inputs",
        "Exercise input handling",
        depends_on=("api-schema",),
        checklist=_items(
            (
                "content-types-checked",
                "Content types checked",
                "Try documented and adjacent types.",
                True,
            ),
            (
                "error-shape-recorded",
                "Error shapes recorded",
                "Note leaked stack traces or internals.",
                False,
            ),
        ),
        minutes=18,
        tags=("api", "input"),
    ),
    _step(
        "api-summary",
        "Summarize API findings",
        kind=StepKind.VERIFICATION,
        depends_on=("api-authz", "api-inputs"),
        checklist=_items(
            (
                "findings-linked",
                "Findings linked to endpoints",
                "Use stable endpoint identifiers.",
                True,
            ),
            (
                "requests-exported",
                "Requests exported",
                "Store sanitized request and response pairs.",
                True,
            ),
        ),
        minutes=12,
        variables=("finding_id",),
    ),
)

_API_PLAYBOOK = Playbook(
    id=5,
    key="api-security-checks",
    title="API security checks",
    description="Endpoint inventory, authorization checks, and input handling review.",
    status=PlaybookStatus.ACTIVE,
    category="api",
    tags=("api", "authorization", "review"),
    version="1.0.0",
    steps=_API_STEPS,
    variables=(_SCOPE, _FINDING),
    created_at="2026-02-01T00:00:00+00:00",
    updated_at="2026-02-22T00:00:00+00:00",
)

_FORENSIC_STEPS = (
    _step(
        "case-open",
        "Open forensic case",
        kind=StepKind.NOTE,
        summary="Record the case identifier, examiner, and acquisition scope.",
        checklist=_items(
            ("case-recorded", "Case recorded", "Use a stable identifier.", True),
            ("examiner-recorded", "Examiner recorded", "Name the responsible operator.", True),
        ),
        variables=("case_id", "operator"),
        minutes=4,
    ),
    _step(
        "acquire",
        "Acquire artifact",
        depends_on=("case-open",),
        command="sha256sum {{ target }} | tee {{ evidence_dir }}/hashes.txt",
        checklist=_items(
            ("hash-captured", "Hash captured", "Record SHA-256 before analysis.", True),
            ("original-preserved", "Original preserved", "Work on a verified copy.", True),
        ),
        minutes=12,
        variables=("evidence_dir",),
    ),
    _step(
        "timeline",
        "Build a timeline",
        depends_on=("acquire",),
        checklist=_items(
            ("timestamps-normalized", "Timestamps normalized", "Record timezone and source.", True),
            ("gaps-noted", "Gaps noted", "Mark missing or unreliable ranges.", False),
        ),
        minutes=20,
    ),
    _step(
        "artifact-review",
        "Review extracted artifacts",
        snippet="binwalk",
        depends_on=("acquire",),
        command="binwalk -e {{ target }}",
        checklist=_items(
            (
                "files-classified",
                "Files classified",
                "Mark relevant and irrelevant artifacts.",
                True,
            ),
            ("chain-preserved", "Chain of custody preserved", "Log every copy and transfer.", True),
        ),
        minutes=25,
    ),
    _step(
        "case-close",
        "Close case notes",
        kind=StepKind.VERIFICATION,
        depends_on=("timeline", "artifact-review"),
        checklist=_items(
            ("findings-summarized", "Findings summarized", "Link each claim to evidence.", True),
            ("hash-verified", "Hashes verified", "Confirm the original is unchanged.", True),
        ),
        minutes=8,
    ),
)

_FORENSIC_PLAYBOOK = Playbook(
    id=6,
    key="forensics-triage",
    title="Forensic artifact triage",
    description="Acquisition, hashing, timeline, and artifact review for local evidence.",
    status=PlaybookStatus.ACTIVE,
    category="forensics",
    tags=("forensics", "evidence", "triage"),
    version="1.1.0",
    steps=_FORENSIC_STEPS,
    variables=(_CASE, _EVIDENCE, _OPERATOR),
    created_at="2026-01-18T00:00:00+00:00",
    updated_at="2026-02-11T00:00:00+00:00",
)

_HANDOFF_STEPS = (
    _step(
        "package-list",
        "List deliverables",
        kind=StepKind.NOTE,
        checklist=_items(
            ("deliverables-agreed", "Deliverables agreed", "Confirm the contract list.", True),
            ("recipients-recorded", "Recipients recorded", "Use approved addresses only.", True),
        ),
        minutes=5,
    ),
    _step(
        "redact",
        "Redact sensitive material",
        depends_on=("package-list",),
        checklist=_items(
            ("secrets-removed", "Secrets removed", "Scan for tokens and private keys.", True),
            (
                "third-party-data-removed",
                "Third-party data removed",
                "Remove unrelated personal data.",
                True,
            ),
        ),
        minutes=18,
    ),
    _step(
        "verify",
        "Verify bundle integrity",
        kind=StepKind.VERIFICATION,
        depends_on=("redact",),
        checklist=_items(
            ("manifest-generated", "Manifest generated", "Include file sizes and hashes.", True),
            ("checksums-matched", "Checksums matched", "Recompute and compare.", True),
        ),
        minutes=8,
    ),
    _step(
        "handoff",
        "Record handoff",
        kind=StepKind.VERIFICATION,
        depends_on=("verify",),
        checklist=_items(
            ("transfer-logged", "Transfer logged", "Record method, time, and recipient.", True),
            ("retention-noted", "Retention noted", "Record local deletion date.", False),
        ),
        minutes=5,
        variables=("case_id",),
    ),
)

_HANDOFF_PLAYBOOK = Playbook(
    id=7,
    key="evidence-handoff",
    title="Evidence handoff",
    description="Redaction, integrity verification, and transfer logging for deliverables.",
    status=PlaybookStatus.DRAFT,
    category="evidence",
    tags=("evidence", "handoff", "reporting"),
    version="0.4.0",
    steps=_HANDOFF_STEPS,
    variables=(_CASE, _EVIDENCE),
    created_at="2026-02-05T00:00:00+00:00",
    updated_at="2026-02-06T00:00:00+00:00",
)

_IR_STEPS = (
    _step(
        "triage-alert",
        "Triage the alert",
        kind=StepKind.DECISION,
        summary="Classify severity and confirm the affected asset.",
        checklist=_items(
            ("severity-set", "Severity set", "Record initial and current severity.", True),
            ("asset-identified", "Asset identified", "Link the affected host or account.", True),
        ),
        minutes=8,
        variables=("case_id",),
    ),
    _step(
        "preserve",
        "Preserve volatile data",
        depends_on=("triage-alert",),
        checklist=_items(
            ("logs-exported", "Logs exported", "Preserve original timestamps.", True),
            (
                "memory-noted",
                "Memory capture decision recorded",
                "Explain capture or no-capture.",
                False,
            ),
        ),
        minutes=12,
    ),
    _step(
        "contain",
        "Coordinate containment",
        kind=StepKind.DECISION,
        depends_on=("preserve",),
        when=(_condition("scope", ConditionOperator.EXISTS),),
        checklist=_items(
            ("owner-notified", "Owner notified", "Record who approved containment.", True),
            ("action-logged", "Action logged", "Record exact time and change.", True),
        ),
        minutes=10,
        variables=("scope",),
    ),
    _step(
        "scope-impact",
        "Determine impact",
        depends_on=("contain",),
        checklist=_items(
            (
                "affected-accounts-listed",
                "Affected accounts listed",
                "Mark confidence per account.",
                True,
            ),
            (
                "lateral-movement-reviewed",
                "Lateral movement reviewed",
                "Note observed or suspected paths.",
                False,
            ),
        ),
        minutes=20,
    ),
    _step(
        "incident-report",
        "Write incident summary",
        kind=StepKind.VERIFICATION,
        depends_on=("scope-impact",),
        checklist=_items(
            (
                "timeline-complete",
                "Timeline complete",
                "Include detection and response events.",
                True,
            ),
            (
                "actions-tracked",
                "Follow-up actions tracked",
                "Assign an owner to each action.",
                True,
            ),
        ),
        minutes=15,
        variables=("finding_id",),
    ),
)

_IR_PLAYBOOK = Playbook(
    id=8,
    key="incident-response",
    title="Incident response triage",
    description="Alert triage, preservation, containment coordination, and reporting.",
    status=PlaybookStatus.ACTIVE,
    category="incident",
    tags=("incident", "triage", "response"),
    version="1.0.0",
    steps=_IR_STEPS,
    variables=(_CASE, _SCOPE, _FINDING),
    created_at="2026-03-01T00:00:00+00:00",
    updated_at="2026-03-04T00:00:00+00:00",
)

PLAYBOOKS: tuple[Playbook, ...] = (
    _WEB_PLAYBOOK,
    _HOST_PLAYBOOK,
    _CTF_PLAYBOOK,
    _AD_PLAYBOOK,
    _API_PLAYBOOK,
    _FORENSIC_PLAYBOOK,
    _HANDOFF_PLAYBOOK,
    _IR_PLAYBOOK,
)

PLAYBOOK_BY_KEY: dict[str, Playbook] = {playbook.key: playbook for playbook in PLAYBOOKS}


def get_playbook(key: str) -> Playbook | None:
    """Return a built-in playbook by key."""
    return PLAYBOOK_BY_KEY.get(key.strip().casefold())


def playbook_keys() -> tuple[str, ...]:
    """Return all built-in playbook keys."""
    return tuple(PLAYBOOK_BY_KEY)
