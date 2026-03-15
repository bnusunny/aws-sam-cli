# Fix: Add arm64 support for provided.al2023 runtime
SUPPORTED_ARCHITECTURES = {
    "python3.12": ["x86_64", "arm64"],
    "python3.13": ["x86_64", "arm64"],
    "nodejs20.x": ["x86_64", "arm64"],
    "provided.al2023": ["x86_64", "arm64"],  # Fixed: was missing arm64
    "provided.al2": ["x86_64", "arm64"],
}

def validate_architecture(runtime: str, architecture: str) -> bool:
    """Validate that the given architecture is supported for the runtime."""
    supported = SUPPORTED_ARCHITECTURES.get(runtime, ["x86_64"])
    return architecture in supported
