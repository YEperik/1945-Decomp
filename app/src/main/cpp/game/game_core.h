#ifndef PORT1945_GAME_CORE_H
#define PORT1945_GAME_CORE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GAME_LOGICAL_WIDTH 320
#define GAME_LOGICAL_HEIGHT 240
#define GAME_FIXED_STEP (1.0f / 60.0f)
#define GAME_MAX_PLAYER_BULLETS 48
#define GAME_MAX_ENEMIES 12
#define GAME_MAX_ENEMY_SHOTS 32

typedef enum GameState {
    GAME_STATE_READY = 0,
    GAME_STATE_PLAYING = 1,
    GAME_STATE_PAUSED = 2,
    GAME_STATE_GAME_OVER = 3
} GameState;

typedef enum GameAudioEvent {
    GAME_AUDIO_NONE = 0,
    GAME_AUDIO_START = 1u << 0,
    GAME_AUDIO_FIRE = 1u << 1,
    GAME_AUDIO_ENEMY_DOWN = 1u << 2,
    GAME_AUDIO_PLAYER_HIT = 1u << 3,
    GAME_AUDIO_GAME_OVER = 1u << 4,
    GAME_AUDIO_PAUSE = 1u << 5
} GameAudioEvent;

typedef struct GameInput {
    float move_x;       /* normalized [-1, 1] */
    float move_y;       /* normalized [-1, 1] */
    uint8_t fire_down;
    uint8_t pause_pressed; /* one-frame edge, not a held state */
} GameInput;

typedef struct GameBullet {
    float x;
    float y;
    float vy;
    uint8_t active;
} GameBullet;

typedef struct GameEnemy {
    float x;
    float y;
    float vx;
    float vy;
    float shot_timer;
    uint8_t active;
} GameEnemy;

typedef struct GameEnemyShot {
    float x;
    float y;
    float vx;
    float vy;
    uint8_t active;
} GameEnemyShot;

typedef struct GameWorld {
    GameState state;
    float accumulator;
    float elapsed;
    float spawn_timer;
    float fire_timer;
    float invulnerability_timer;
    float player_x;
    float player_y;
    uint32_t rng_state;
    uint32_t score;
    int32_t lives;
    uint32_t tick_count;
    uint8_t pause_latched;
    GameBullet player_bullets[GAME_MAX_PLAYER_BULLETS];
    GameEnemy enemies[GAME_MAX_ENEMIES];
    GameEnemyShot enemy_shots[GAME_MAX_ENEMY_SHOTS];
} GameWorld;

/* This is an explicitly-labelled native prototype, not reconstructed PS2 logic. */
void game_world_init(GameWorld *world, uint32_t seed);
void game_world_reset(GameWorld *world, uint32_t seed);
uint32_t game_world_update(GameWorld *world, float delta_seconds, GameInput input);
void game_world_force_pause(GameWorld *world);

#ifdef __cplusplus
}
#endif

#endif
