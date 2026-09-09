/* CodaMND: documented CPython 3.14 embedding API, no generic freezer.
 * Only the private runtime beside this EXE is loaded. No shell, extraction,
 * download, interpreter command-line options, or PATH-based runtime discovery.
 */
#define WIN32_LEAN_AND_MEAN
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

/* Public opaque API: https://docs.python.org/3.14/c-api/init_config.html */
typedef struct PyInitConfig PyInitConfig;
typedef PyInitConfig *(__cdecl *ConfigCreate)(void);
typedef void (__cdecl *ConfigFree)(PyInitConfig *);
typedef int (__cdecl *ConfigInt)(PyInitConfig *, const char *, int64_t);
typedef int (__cdecl *ConfigStr)(PyInitConfig *, const char *, const char *);
typedef int (__cdecl *ConfigList)(PyInitConfig *, const char *, size_t, char *const *);
typedef int (__cdecl *ConfigError)(PyInitConfig *, const char **);
typedef int (__cdecl *ConfigInitialize)(PyInitConfig *);
typedef int (__cdecl *RunMain)(void);

static wchar_t *join_path(const wchar_t *root, const wchar_t *suffix) {
    size_t a = wcslen(root), b = wcslen(suffix);
    if (a + b >= 32767) return NULL;
    wchar_t *result = calloc(a + b + 1, sizeof(wchar_t));
    if (result) {
        memcpy(result, root, a * sizeof(wchar_t));
        memcpy(result + a, suffix, (b + 1) * sizeof(wchar_t));
    }
    return result;
}

static char *utf8(const wchar_t *value) {
    int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1, NULL, 0, NULL, NULL);
    if (!size) return NULL;
    char *result = malloc((size_t)size);
    if (result && !WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value, -1, result, size, NULL, NULL)) {
        free(result);
        return NULL;
    }
    return result;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show) {
    (void)instance; (void)previous; (void)command; (void)show;
    int result = 1, argc = 0, diagnostic = 0;
    wchar_t *exe = calloc(32768, sizeof(wchar_t)), *root = NULL;
    wchar_t *library = NULL, *archive = NULL, *runtime_path = NULL;
    char *exe_utf8 = NULL, *root_utf8 = NULL, *paths[2] = {NULL, NULL};
    char **args = NULL;
    wchar_t **wide_args = CommandLineToArgvW(GetCommandLineW(), &argc);
    PyInitConfig *config = NULL;
    ConfigFree config_free = NULL;
    ConfigError config_error = NULL;
    const wchar_t *message = L"Impossible de démarrer CodaMND. Extrayez le dossier portable au complet.";
    if (wide_args && argc > 1) diagnostic = wcscmp(wide_args[1], L"--diagnostic") == 0;
    if (!exe || !wide_args || argc < 1) goto done;
    DWORD length = GetModuleFileNameW(NULL, exe, 32768);
    if (!length || length >= 32768) goto done;
    root = join_path(exe, L"");
    if (!root) goto done;
    wchar_t *separator = wcsrchr(root, L'\\');
    if (!separator) goto done;
    *separator = L'\0';
    library = join_path(root, L"\\lib");
    archive = join_path(root, L"\\lib\\library.zip");
    runtime_path = join_path(root, L"\\python314.dll");
    if (!library || !archive || !runtime_path) goto done;

    /* Exclude the current directory and PATH before loading the Python DLL. */
    if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_APPLICATION_DIR |
                                 LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS)) goto done;
    if (!AddDllDirectory(library)) goto done;
    HMODULE runtime = LoadLibraryExW(runtime_path, NULL,
        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!runtime) goto done;
    /* Keep runtime and DLL directory registered until process exit. */
#define BIND(type, local, symbol) \
    type local = (type)(void *)GetProcAddress(runtime, symbol); \
    if (!local) goto done
    BIND(ConfigCreate, config_create, "PyInitConfig_Create");
    config_free = (ConfigFree)(void *)GetProcAddress(runtime, "PyInitConfig_Free");
    config_error = (ConfigError)(void *)GetProcAddress(runtime, "PyInitConfig_GetError");
    if (!config_free || !config_error) goto done;
    BIND(ConfigInt, config_int, "PyInitConfig_SetInt");
    BIND(ConfigStr, config_str, "PyInitConfig_SetStr");
    BIND(ConfigList, config_list, "PyInitConfig_SetStrList");
    BIND(ConfigInitialize, initialize, "Py_InitializeFromInitConfig");
    BIND(RunMain, run_main, "Py_RunMain");
#undef BIND

    exe_utf8 = utf8(exe);
    root_utf8 = utf8(root);
    paths[0] = utf8(archive);
    paths[1] = utf8(library);
    args = calloc((size_t)argc, sizeof(char *));
    if (!exe_utf8 || !root_utf8 || !paths[0] || !paths[1] || !args) goto done;
    for (int i = 0; i < argc; i++) {
        args[i] = utf8(i == 0 ? exe : wide_args[i]);
        if (!args[i]) goto done;
    }
    config = config_create();  /* Isolated defaults; never read PYTHONPATH. */
    if (!config) goto done;
#define SET_INT(name, value) if (config_int(config, name, value) < 0) goto done
#define SET_STR(name, value) if (config_str(config, name, value) < 0) goto done
    SET_INT("parse_argv", 0);
    SET_INT("use_environment", 0);
    SET_INT("site_import", 0);
    SET_INT("user_site_directory", 0);
    SET_INT("write_bytecode", 0);
    SET_INT("safe_path", 1);
    SET_INT("utf8_mode", 1);
    SET_INT("remote_debug", 0);
    SET_INT("module_search_paths_set", 1);
    SET_STR("program_name", exe_utf8);
    SET_STR("executable", exe_utf8);
    SET_STR("home", root_utf8);
    SET_STR("prefix", root_utf8);
    SET_STR("exec_prefix", root_utf8);
    SET_STR("run_module", "_codamnd_native");
    if (config_list(config, "module_search_paths", 2, paths) < 0 ||
        config_list(config, "argv", (size_t)argc, args) < 0) goto done;
    if (initialize(config) < 0) goto done;
    config_free(config);
    config = NULL;
    result = run_main();
    message = NULL;  /* Application entry handles its own failures. */

done:
    if (message && !diagnostic) MessageBoxW(NULL, message, L"CodaMND", MB_OK | MB_ICONERROR);
    if (config && config_error) {
        const char *detail = NULL;
        if (config_error(config, &detail) == 1 && detail) {
            /* Diagnostic builds can capture stderr; never log payroll data. */
            DWORD written;
            HANDLE error = GetStdHandle(STD_ERROR_HANDLE);
            if (error && error != INVALID_HANDLE_VALUE) WriteFile(error, detail, (DWORD)strlen(detail), &written, NULL);
        }
    }
    if (config && config_free) config_free(config);
    if (args) { for (int i = 0; i < argc; i++) free(args[i]); free(args); }
    if (wide_args) LocalFree(wide_args);
    free(exe); free(root); free(library); free(archive); free(runtime_path);
    free(exe_utf8); free(root_utf8); free(paths[0]); free(paths[1]);
    return result;
}
