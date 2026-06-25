    # Fallback: when parent inheritance produces a falsy key (e.g. parent was
    # initialized with an empty-string api_key), resolve from the runtime provider.
    if not effective_api_key and effective_provider:
        try:
            from hermes_cli.runtime_provider import resolve_runtime_provider
            fallback_runtime = resolve_runtime_provider(
                requested=effective_provider, target_model=effective_model
            )
            effective_api_key = fallback_runtime.get("api_key") or effective_api_key
            if effective_api_key and not override_base_url:
                effective_base_url = (
                    fallback_runtime.get("base_url") or effective_base_url
                )
        except Exception:
            pass  # don't break the build if runtime resolution fails
