"""Reports the repository's license.

For GitHub repos: GitHub already runs its own license-detection library
(licensee) against every repository and returns the result directly in the
repo API response — using that is not a guess, it's GitHub's own
authoritative determination. See github_client.fetch_repo_details(), which
captures license_spdx_id / license_name from that response.

"""

import re
from typing import Optional

# (display name, SPDX-ish id, [phrases that must ALL be present])
# Ordered so a more specific check (e.g. GPL v3) is tried before a more
# generic one that could also match its text.
_KNOWN_LICENSES = [
    ("MIT License", "MIT", ["permission is hereby granted, free of charge", "mit license"]),
    ("Apache License 2.0", "Apache-2.0", ["apache license", "version 2.0"]),
    ("GNU General Public License v3.0", "GPL-3.0", ["gnu general public license", "version 3"]),
    ("GNU General Public License v2.0", "GPL-2.0", ["gnu general public license", "version 2"]),
    ("GNU Lesser General Public License v3.0", "LGPL-3.0", ["gnu lesser general public license", "version 3"]),
    ("GNU Lesser General Public License v2.1", "LGPL-2.1", ["gnu lesser general public license", "version 2.1"]),
    ("Mozilla Public License 2.0", "MPL-2.0", ["mozilla public license", "version 2.0"]),
    ("BSD 3-Clause License", "BSD-3-Clause", ["redistribution and use in source and binary forms", "neither the name of"]),
    ("ISC License", "ISC", ["isc license", "permission to use, copy, modify, and/or distribute"]),
    ("The Unlicense", "Unlicense", ["this is free and unencumbered software released into the public domain"]),
]


def summarize_license_github(license_spdx_id: Optional[str], license_name: Optional[str]) -> dict:
    """From GitHub's own license-detection result (repo API response)."""
    if not license_spdx_id or license_spdx_id == "NOASSERTION":
        if license_name:
            # GitHub found a LICENSE file but couldn't confidently identify it.
            return {
                "available": True,
                "detected": False,
                "license_name": license_name,
                "spdx_id": None,
                "message": f'A license file exists ("{license_name}") but GitHub could not confidently identify its type.',
            }
        return {
            "available": True,
            "detected": False,
            "license_name": None,
            "spdx_id": None,
            "message": "No license detected.",
        }
    return {
        "available": True,
        "detected": True,
        "license_name": license_name or license_spdx_id,
        "spdx_id": license_spdx_id,
        "message": None,
    }
