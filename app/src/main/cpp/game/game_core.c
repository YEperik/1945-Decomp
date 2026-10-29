#include "game_core.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define PLAYER_SPEED 100.0f
#define PLAYER_MIN_X 9.0f
#define PLAYER_MAX_X 311.0f
#define PLAYER_MIN_Y 35.0f
#define PLAYER_MAX_Y 229.0f
#define PLAYER_BULLET_SPEED 170.0f
#define ENEMY_SHOT_SPEED 58.0f
#define MAX_FRAME_SECONDS (GAME_FIXED_STEP * 5.0f)
#define PI_F 3.14159265358979323846f

static float clamp_float(float value, float min_value, float max_value)
{
    if (!isfinite(value)) {
        return 0.0f;
    }
    if (value < min_value) {
        return min_value;
    }
    if (value > max_value) {
        return max_value;
    }
    return value;
}

static uint32_t random_u32(GameWorld *world)
{
    uint32_t x = world->rng_state;
    if (x == 0u) {
        x = 0x1945a11u;
    }
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    world->rng_state = x;
    return x;
}

static int intersects(float ax, float ay, float ar, float bx, float by, float br)
{
    float dx = ax - bx;
    float dy = ay - by;
    float radius = ar + br;
    return dx * dx + dy * dy <= radius * radius;
}

void game_world_reset(GameWorld *world, uint32_t seed)
{
    if (world == NULL) {
        return;
    }
    (void)memset(world, 0, sizeof(*world));
    world->state = GAME_STATE_READY;
    world->player_x = GAME_LOGICAL_WIDTH * 0.5f;
    world->player_y = GAME_LOGICAL_HEIGHT - 32.0f;
    world->lives = 3;
    world->spawn_timer = 0.4f;
    world->rng_state = seed == 0u ? 0x1945a11u : seed;
}

void game_world_init(GameWorld *world, uint32_t seed)
{
    game_world_reset(world, seed);
}

void game_world_force_pause(GameWorld *world)
{
    if (world != NULL && world->state == GAME_STATE_PLAYING) {
        world->state = GAME_STATE_PAUSED;
        /* A lifecycle pause wins over any unconsumed one-frame pause edge. */
        world->pause_latched = 0u;
        world->accumulator = 0.0f;
    }
}

static GameBullet *alloc_player_bullet(GameWorld *world)
{
    size_t i;
    for (i = 0u; i < GAME_MAX_PLAYER_BULLETS; ++i) {
        if (world->player_bullets[i].active == 0u) {
            return &world->player_bullets[i];
        }
    }
    return NULL;
}

static GameEnemy *alloc_enemy(GameWorld *world)
{
    size_t i;
    for (i = 0u; i < GAME_MAX_ENEMIES; ++i) {
        if (world->enemies[i].active == 0u) {
            return &world->enemies[i];
        }
    }
    return NULL;
}

static GameEnemyShot *alloc_enemy_shot(GameWorld *world)
{
    size_t i;
    for (i = 0u; i < GAME_MAX_ENEMY_SHOTS; ++i) {
        if (world->enemy_shots[i].active == 0u) {
            return &world->enemy_shots[i];
        }
    }
    return NULL;
}

static void spawn_enemy(GameWorld *world)
{
    GameEnemy *enemy = alloc_enemy(world);
    uint32_t r;
    if (enemy == NULL) {
        return;
    }
    r = random_u32(world);
    enemy->x = 16.0f + (float)(r % 289u);
    enemy->y = -8.0f;
    enemy->vx = (float)((int32_t)((r >> 10) % 61u) - 30) * 0.45f;
    enemy->vy = 19.0f + (float)((r >> 18) % 11u);
    enemy->shot_timer = 0.8f + (float)((r >> 3) % 120u) / 100.0f;
    enemy->active = 1u;
}

static void spawn_enemy_shot(GameWorld *world, const GameEnemy *enemy)
{
    GameEnemyShot *shot = alloc_enemy_shot(world);
    float dx;
    float dy;
    float length;
    if (shot == NULL) {
        return;
    }
    dx = world->player_x - enemy->x;
    dy = world->player_y - enemy->y;
    length = sqrtf(dx * dx + dy * dy);
    if (length < 0.001f) {
        length = 1.0f;
    }
    shot->x = enemy->x;
    shot->y = enemy->y + 5.0f;
    shot->vx = dx / length * ENEMY_SHOT_SPEED;
    shot->vy = dy / length * ENEMY_SHOT_SPEED;
    shot->active = 1u;
}

static uint32_t game_step(GameWorld *world, const GameInput *input)
{
    uint32_t events = GAME_AUDIO_NONE;
    size_t i;
    size_t j;
    float move_x = clamp_float(input->move_x, -1.0f, 1.0f);
    float move_y = clamp_float(input->move_y, -1.0f, 1.0f);
    float magnitude = sqrtf(move_x * move_x + move_y * move_y);

    world->tick_count += 1u;
    if (magnitude > 1.0f) {
        move_x /= magnitude;
        move_y /= magnitude;
    }

    if (world->state == GAME_STATE_READY) {
        if (input->fire_down != 0u) {
            world->state = GAME_STATE_PLAYING;
            events |= GAME_AUDIO_START;
        } else {
            return events;
        }
    } else if (world->state == GAME_STATE_GAME_OVER) {
        if (input->fire_down != 0u) {
            uint32_t seed = random_u32(world) ^ world->tick_count;
            game_world_reset(world, seed);
            world->state = GAME_STATE_PLAYING;
            events |= GAME_AUDIO_START;
        } else {
            return events;
        }
    } else if (world->state == GAME_STATE_PAUSED) {
        if (input->pause_pressed != 0u) {
            world->state = GAME_STATE_PLAYING;
            events |= GAME_AUDIO_PAUSE;
        }
        return events;
    } else if (input->pause_pressed != 0u) {
        world->state = GAME_STATE_PAUSED;
        events |= GAME_AUDIO_PAUSE;
        return events;
    }

    world->elapsed += GAME_FIXED_STEP;
    if (world->invulnerability_timer > 0.0f) {
        world->invulnerability_timer -= GAME_FIXED_STEP;
        if (world->invulnerability_timer < 0.0f) {
            world->invulnerability_timer = 0.0f;
        }
    }

    world->player_x = clamp_float(world->player_x + move_x * PLAYER_SPEED * GAME_FIXED_STEP,
                                  PLAYER_MIN_X, PLAYER_MAX_X);
    world->player_y = clamp_float(world->player_y + move_y * PLAYER_SPEED * GAME_FIXED_STEP,
                                  PLAYER_MIN_Y, PLAYER_MAX_Y);

    world->fire_timer -= GAME_FIXED_STEP;
    if (input->fire_down != 0u && world->fire_timer <= 0.0f) {
        GameBullet *bullet = alloc_player_bullet(world);
        if (bullet != NULL) {
            bullet->x = world->player_x;
            bullet->y = world->player_y - 7.0f;
            bullet->vy = -PLAYER_BULLET_SPEED;
            bullet->active = 1u;
            events |= GAME_AUDIO_FIRE;
        }
        world->fire_timer = 0.17f;
    }

    world->spawn_timer -= GAME_FIXED_STEP;
    if (world->spawn_timer <= 0.0f) {
        spawn_enemy(world);
        world->spawn_timer = 0.78f + (float)(random_u32(world) % 50u) / 100.0f;
    }

    for (i = 0u; i < GAME_MAX_PLAYER_BULLETS; ++i) {
        GameBullet *bullet = &world->player_bullets[i];
        if (bullet->active == 0u) {
            continue;
        }
        bullet->y += bullet->vy * GAME_FIXED_STEP;
        if (bullet->y < -5.0f) {
            bullet->active = 0u;
        }
    }

    for (i = 0u; i < GAME_MAX_ENEMIES; ++i) {
        GameEnemy *enemy = &world->enemies[i];
        if (enemy->active == 0u) {
            continue;
        }
        enemy->x += enemy->vx * GAME_FIXED_STEP;
        enemy->y += enemy->vy * GAME_FIXED_STEP;
        if (enemy->x < 8.0f || enemy->x > 312.0f) {
            enemy->vx = -enemy->vx;
            enemy->x = clamp_float(enemy->x, 8.0f, 312.0f);
        }
        enemy->shot_timer -= GAME_FIXED_STEP;
        if (enemy->shot_timer <= 0.0f) {
            spawn_enemy_shot(world, enemy);
            enemy->shot_timer = 1.15f + (float)(random_u32(world) % 90u) / 100.0f;
        }
        if (enemy->y > GAME_LOGICAL_HEIGHT + 10.0f) {
            enemy->active = 0u;
        }
    }

    for (i = 0u; i < GAME_MAX_PLAYER_BULLETS; ++i) {
        GameBullet *bullet = &world->player_bullets[i];
        if (bullet->active == 0u) {
            continue;
        }
        for (j = 0u; j < GAME_MAX_ENEMIES; ++j) {
            GameEnemy *enemy = &world->enemies[j];
            if (enemy->active != 0u && intersects(bullet->x, bullet->y, 2.0f,
                                                  enemy->x, enemy->y, 6.0f)) {
                bullet->active = 0u;
                enemy->active = 0u;
                world->score += 100u;
                events |= GAME_AUDIO_ENEMY_DOWN;
                break;
            }
        }
    }

    for (i = 0u; i < GAME_MAX_ENEMY_SHOTS; ++i) {
        GameEnemyShot *shot = &world->enemy_shots[i];
        if (shot->active == 0u) {
            continue;
        }
        shot->x += shot->vx * GAME_FIXED_STEP;
        shot->y += shot->vy * GAME_FIXED_STEP;
        if (shot->x < -5.0f || shot->x > GAME_LOGICAL_WIDTH + 5.0f ||
            shot->y < -5.0f || shot->y > GAME_LOGICAL_HEIGHT + 5.0f) {
            shot->active = 0u;
        } else if (world->invulnerability_timer <= 0.0f &&
                   intersects(shot->x, shot->y, 2.5f,
                              world->player_x, world->player_y, 5.0f)) {
            shot->active = 0u;
            world->lives -= 1;
            world->invulnerability_timer = 1.15f;
            events |= GAME_AUDIO_PLAYER_HIT;
            if (world->lives <= 0) {
                world->lives = 0;
                world->state = GAME_STATE_GAME_OVER;
                events |= GAME_AUDIO_GAME_OVER;
                break;
            }
        }
    }

    if (world->state == GAME_STATE_PLAYING && world->invulnerability_timer <= 0.0f) {
        for (i = 0u; i < GAME_MAX_ENEMIES; ++i) {
            GameEnemy *enemy = &world->enemies[i];
            if (enemy->active != 0u &&
                intersects(enemy->x, enemy->y, 6.0f,
                           world->player_x, world->player_y, 5.0f)) {
                enemy->active = 0u;
                world->lives -= 1;
                world->invulnerability_timer = 1.15f;
                events |= GAME_AUDIO_PLAYER_HIT;
                if (world->lives <= 0) {
                    world->lives = 0;
                    world->state = GAME_STATE_GAME_OVER;
                    events |= GAME_AUDIO_GAME_OVER;
                }
                break;
            }
        }
    }

    return events;
}

uint32_t game_world_update(GameWorld *world, float delta_seconds, GameInput input)
{
    uint32_t events = GAME_AUDIO_NONE;
    unsigned int steps = 0u;
    uint8_t pause_pending;

    if (world == NULL || !isfinite(delta_seconds) || delta_seconds <= 0.0f) {
        return events;
    }
    if (delta_seconds > MAX_FRAME_SECONDS) {
        delta_seconds = MAX_FRAME_SECONDS;
    }
    input.move_x = clamp_float(input.move_x, -1.0f, 1.0f);
    input.move_y = clamp_float(input.move_y, -1.0f, 1.0f);
    input.fire_down = input.fire_down != 0u ? 1u : 0u;
    input.pause_pressed = input.pause_pressed != 0u ? 1u : 0u;
    if (input.pause_pressed != 0u) {
        world->pause_latched = 1u;
    }
    pause_pending = world->pause_latched;

    world->accumulator += delta_seconds;
    while (world->accumulator >= GAME_FIXED_STEP && steps < 5u) {
        GameInput step_input = input;
        step_input.pause_pressed = pause_pending;
        events |= game_step(world, &step_input);
        pause_pending = 0u;
        world->pause_latched = 0u;
        world->accumulator -= GAME_FIXED_STEP;
        steps += 1u;
    }
    if (steps == 5u && world->accumulator >= GAME_FIXED_STEP) {
        world->accumulator = 0.0f;
    }
    return events;
}
