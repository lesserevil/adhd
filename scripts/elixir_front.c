/* Linux ELF front door for a pinned official Elixir launcher.
 * Every argument is delegated unchanged after checking the launcher's exact
 * bytes against a build-time pin. No validation or test result is substituted.
 * Compile with ADHD_ELIXIR_SCRIPT and a generated ADHD_ELIXIR_PINNED_BYTES array.
 */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#ifndef ADHD_ELIXIR_SCRIPT
#error ADHD_ELIXIR_SCRIPT must identify the official Elixir launcher
#endif
#ifndef ADHD_ELIXIR_PINNED_BYTES
#error ADHD_ELIXIR_PINNED_BYTES must bind its exact bytes
#endif
int main(int argc, char **argv) {
    static const unsigned char pinned[] = ADHD_ELIXIR_PINNED_BYTES;
    FILE *file = fopen(ADHD_ELIXIR_SCRIPT, "rb");
    unsigned char buffer[4096];
    size_t count, offset = 0;
    if (!file) return 126;
    while ((count = fread(buffer, 1, sizeof buffer, file)) != 0) {
        if (offset + count > sizeof pinned || memcmp(buffer, pinned + offset, count)) {
            fclose(file);
            fputs("Pinned Elixir launcher changed\n", stderr);
            return 126;
        }
        offset += count;
    }
    if (ferror(file) || fclose(file) || offset != sizeof pinned) return 126;
    (void)argc;
    argv[0] = ADHD_ELIXIR_SCRIPT;
    execv(ADHD_ELIXIR_SCRIPT, argv);
    fputs("Elixir launcher unavailable\n", stderr);
    return 127;
}
