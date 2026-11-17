/* ScreenPlay integration for OpenTTD. GPL-2.0, matching the upstream engine. */
#ifndef SCREENPLAY_BRIDGE_H
#define SCREENPLAY_BRIDGE_H
bool ScreenPlayEnabled();
bool ScreenPlayRejectModeSwitch();
void ScreenPlayNewGame();
bool ScreenPlayAllowUpdate();
void ScreenPlayPublish();
#endif
