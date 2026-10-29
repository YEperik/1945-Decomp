#ifndef PORT1945_GAME_RENDERER_H
#define PORT1945_GAME_RENDERER_H

#include "game_core.h"

#ifdef __cplusplus
extern "C" {
#endif

void game_renderer_surface_created(void);
void game_renderer_surface_changed(int width, int height);
void game_renderer_draw(const GameWorld *world);

#ifdef __cplusplus
}
#endif

#endif
