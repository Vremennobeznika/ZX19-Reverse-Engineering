/* Test-only DLL entry, with no CRT or Windows API dependencies. */
int DllMainCRTStartup(void *module, unsigned reason, void *reserved) {
    (void)module;
    (void)reason;
    (void)reserved;
    return 1;
}
