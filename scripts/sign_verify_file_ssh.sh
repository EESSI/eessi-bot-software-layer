#!/bin/bash
#
# SSH Signature Signing and Verification Script
# - Sign a file using an SSH private key.
# - Verify a signed file using an allowed signers file.
#
# Generates a signature file named `<file>.sig` in the same directory.
#
# Author: Alan O'Cais
# Author: Thomas Roeblitz
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

# Usage message
usage() {
    local exit_code=${1:-9}
    cat <<EOF
Usage:
  $0 --sign --private-key <private_key> --file <file> [--namespace <namespace>]
  $0 --verify --allowed-signers-file <allowed_signers_file> --file <file> [--signature-file <signature_file>] [--terse]

Options:
  --sign:
    --private-key <private_key>: Path to SSH private key (use KEY_PASSPHRASE env for passphrase)
    --file <file>: File to sign
    --namespace <namespace>: Optional, defaults to "file" if not specified

  --verify:
    --allowed-signers-file <allowed_signers_file>: Path to the allowed signers file
    --file <file>: File to verify
    --signature-file <signature_file>: Optional, defaults to '<file>.sig'
    --terse: If set, output only matching identity and namespace for verification in JSON format

Example allowed signers format:
  identity_1 namespaces="namespace",valid-before="last-valid-day" <public-key>

If the private key has a passphrase, this can be provided via a 'KEY_PASSPHRASE' environment variable.
EOF
    exit "$exit_code"
}

# Error codes
FILE_PROBLEM=1
CONVERSION_FAILURE=2
VALIDATION_FAILED=3

# Ensure minimum arguments
if [ "$#" -lt 3 ]; then
    echo "Error: Missing required arguments."
    usage
fi

# Parse options
TERSE_MODE=false
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --sign)
            MODE="sign"
            shift
            ;;
        --verify)
            MODE="verify"
            shift
            ;;
        --private-key)
            PRIVATE_KEY="$2"
            shift 2
            ;;
        --file)
            FILE_TO_SIGN="$2"
            shift 2
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --allowed-signers-file)
            ALLOWED_SIGNERS_FILE="$2"
            shift 2
            ;;
        --signature-file)
            SIG_FILE="$2"
            shift 2
            ;;
        --terse)
            TERSE_MODE=true
            shift
            ;;
        *)
            echo "Error: Invalid argument: $1"
            usage
            ;;
    esac
done

# Set default namespace if not provided
if [ -z "$NAMESPACE" ]; then
    NAMESPACE="file"
fi

# Ensure mode is set
if [ -z "$MODE" ]; then
    echo "Error: Missing operation mode (either --sign or --verify)"
    usage
fi

# Ensure required arguments
if [ "$MODE" == "sign" ]; then
    [ -z "$PRIVATE_KEY" ] && { echo "Error: --private-key not specified."; usage $FILE_PROBLEM; }
    [ -z "$FILE_TO_SIGN" ] && { echo "Error: --file not specified."; usage $FILE_PROBLEM; }
    SIG_FILE="${FILE_TO_SIGN}.sig"
elif [ "$MODE" == "verify" ]; then
    [ -z "$ALLOWED_SIGNERS_FILE" ] && { echo "Error: --allowed-signers-file not specified."; usage $FILE_PROBLEM; }
    [ -z "$FILE_TO_SIGN" ] && { echo "Error: --file not specified."; usage $FILE_PROBLEM; }
    SIG_FILE="${SIG_FILE:-${FILE_TO_SIGN}.sig}"
fi

# Ensure the target file exists
if [ ! -f "$FILE_TO_SIGN" ]; then
    echo "Error: File '$FILE_TO_SIGN' not found."
    exit $FILE_PROBLEM
fi

# Use a very conservative umask throughout this script since we are dealing with sensitive things
umask 0077 || { echo "Error: Failed to set 0077 umask."; exit $FILE_PROBLEM; }

# Create a restricted temporary directory and ensure cleanup on exit
TEMP_DIR=$(mktemp -d) || { echo "Error: Failed to create temporary directory."; exit $FILE_PROBLEM; }
trap 'rm -rf "$TEMP_DIR"' EXIT

# Converts the SSH private key to OpenSSH format and generates a public key
convert_private_key() {
    local input_key="$1"
    local output_key="$2"

    echo "Converting SSH key to OpenSSH format..."
    cp "$input_key" "$output_key" || { echo "Error: Failed to copy $input_key to $output_key"; exit $FILE_PROBLEM; }

    # This saves the key in the default OpenSSH format (which is required for signing)
    ssh-keygen -p -f "$output_key" -P "${KEY_PASSPHRASE:-}" -N "${KEY_PASSPHRASE:-}" || {
        echo "Error: Failed to convert key to OpenSSH format."
        exit $CONVERSION_FAILURE
    }

    # Extract the public key from the private key
    ssh-keygen -y -f "$input_key" -P "${KEY_PASSPHRASE:-}" > "${output_key}.pub" || {
        echo "Error: Failed to extract public key."
        exit $CONVERSION_FAILURE
    }
}

# Sign mode
if [ "$MODE" == "sign" ]; then
    TEMP_KEY="$TEMP_DIR/converted_key"

    # Check for key and existing signature
    [ ! -f "$PRIVATE_KEY" ] && { echo "Error: Private key not found."; exit $FILE_PROBLEM; }
    [ -f "$SIG_FILE" ] && { echo "Error: Signature already exists. Remove to re-sign."; exit $FILE_PROBLEM; }

    convert_private_key "$PRIVATE_KEY" "$TEMP_KEY"

    echo "Signing the file..."
    ssh-keygen -Y sign -f "$TEMP_KEY" -P "${KEY_PASSPHRASE:-}" -n "${NAMESPACE}" "$FILE_TO_SIGN"

    cat <<EOF

For verification, your allowed signers file could contain:
identity_1 namespaces="${NAMESPACE}",valid-before="LAST_VALID_DAY" $(cat "${TEMP_KEY}.pub")
EOF

    [ ! -f "$SIG_FILE" ] && { echo "Error: Signing failed."; exit $FILE_PROBLEM; }
    echo "Signature created: $SIG_FILE"

    echo "Validating the signature..."
    ssh-keygen -Y check-novalidate -n "${NAMESPACE}" -f "${TEMP_KEY}.pub" -s "$SIG_FILE" < "$FILE_TO_SIGN" || {
        echo "Error: Signature validation failed."
        exit $VALIDATION_FAILED
    }

# Verify mode
elif [ "$MODE" == "verify" ]; then
    # Ensure required files exist
    for file in "$ALLOWED_SIGNERS_FILE" "$SIG_FILE"; do
        [ ! -f "$file" ] && { echo "Error: File '$file' not found."; exit $FILE_PROBLEM; }
    done

    # Iterate through each principal in the allowed signers file
    while read -r principal options key
    do
        [[ -z "$principal" || "$principal" == \#* ]] && continue

        namespaces=$(echo "$options" | grep -oP "namespaces=\"\K[^\"]+")
        
        if [ "$TERSE_MODE" = true ]; then
            if ssh-keygen -Y verify -f "$ALLOWED_SIGNERS_FILE" -n "$namespaces" -I "$principal" -s "$SIG_FILE" < "$FILE_TO_SIGN" > /dev/null 2>&1; then
                # Output in JSON format
                echo "{\"identity\": \"$principal\", \"namespace\": \"$namespaces\"}"
                exit 0
            fi
        else
            if ssh-keygen -Y verify -f "$ALLOWED_SIGNERS_FILE" -n "$namespaces" -I "$principal" -s "$SIG_FILE" < "$FILE_TO_SIGN"; then
                echo "Signature is valid for principal: $principal and namespace: $namespaces"
                exit 0
            else
                echo
                echo "Signature _not_ valid for principal: $principal and namespace: $namespaces"
            fi
        fi
    done < "$ALLOWED_SIGNERS_FILE"

    echo "Error: No valid signature found."
    exit $VALIDATION_FAILED
else
    echo "Error: Invalid operation mode. Use --sign or --verify."
    usage
fi
