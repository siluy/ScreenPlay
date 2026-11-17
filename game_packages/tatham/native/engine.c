/* Trusted validation utility. Never expose this process to a evaluated agent. */
#include "puzzles.h"
#include <string.h>

static void write_save(void *ctx, const void *buf, int len) {
    fwrite(buf, 1, len, (FILE *)ctx);
}

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: screenplay-engine GAME GAME_ID\n"); return 2; }
    const game *g = NULL;
    for (int i = 0; i < gamecount; i++)
        if (!strcmp(argv[1], gamelist[i]->name)) g = gamelist[i];
    if (!g) { fprintf(stderr, "unknown game\n"); return 2; }
    static const drawing_api api = {1, NULL};
    midend *me = midend_new(NULL, g, &api, NULL);
    const char *err = midend_game_id(me, argv[2]);
    if (err) { fprintf(stderr, "%s\n", err); return 2; }
    midend_new_game(me);
    int w = INT_MAX, h = INT_MAX;
    midend_size(me, &w, &h, false, 1.0);
    printf("SIZE %d %d\nSTATUS %d\n", w, h, midend_status(me));
    char line[4096];
    while (fgets(line, sizeof(line), stdin)) {
        if (line[0] == '\n' || line[0] == '\r') continue;
        int x, y, key;
        if (sscanf(line, "input %d %d %d", &x, &y, &key) == 3) {
            midend_process_key(me, x, y, key);
            midend_stop_anim(me);
        } else if (!strncmp(line, "solve", 5)) {
            err = midend_solve(me);
            if (err) printf("ERROR %s\n", err);
        } else if (!strncmp(line, "save", 4)) {
            puts("SAVE_BEGIN"); midend_serialise(me, write_save, stdout); puts("SAVE_END");
        } else if (!strncmp(line, "restart", 7)) {
            midend_restart_game(me);
        } else if (strncmp(line, "status", 6)) {
            fprintf(stderr, "unknown command\n"); return 2;
        }
        printf("STATUS %d\n", midend_status(me));
    }
    midend_free(me);
    return 0;
}
