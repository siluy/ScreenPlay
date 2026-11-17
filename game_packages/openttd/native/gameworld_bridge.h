/* GameWorld integration for OpenTTD. GPL-2.0, matching the upstream engine. */
#ifndef GAMEWORLD_BRIDGE_H
#define GAMEWORLD_BRIDGE_H
bool GameWorldEnabled();
bool GameWorldRejectModeSwitch();
void GameWorldNewGame();
bool GameWorldAllowUpdate();
void GameWorldPublish();
#endif
