"""Build the upstream C++ engines with small, reviewable evaluator hooks."""
from pathlib import Path
import os
import sys
from .build import ROOT, run
from .native_build import patch


def build_compiled(package, prepared, output):
    cmake = str(Path(sys.executable).parent / 'cmake')
    ninja = str(Path(sys.executable).parent / 'ninja')
    flags = ['-G','Ninja',f'-DCMAKE_MAKE_PROGRAM={ninja}','-DCMAKE_BUILD_TYPE=Release',
             '-DCMAKE_PREFIX_PATH=/opt/homebrew;/opt/homebrew/opt/openal-soft']
    if package == 'enigma':
        # Keep the normal game renderer and 10 ms physics step, allowing UI event pumping while frozen.
        p=prepared/'src/game.cc'
        patch(p, '#include "game.hh"', '#include "game.hh"\n#include "../gameworld_bridge.hh"\n#include "player.hh"\n#include "actors.hh"')
        patch(p, '            client::Tick(dtime);\n            server::Tick(dtime);', '''            if (gw::enabled()) {
                bool advance = gw::next();
                double dt = (!gw::ready || advance) ? .01 : 0.;
                client::Tick(dt);
                if (!gw::ready || advance) server::Tick(dt);
                if (auto *a = player::GetMainActor(0)) {
                    const auto &pos = a->getActorInfo().pos;
                    gw::x=pos[0]; gw::y=pos[1];
                }
                gw::nativeTime=server::LevelTime;
                gw::publish();
            } else {
                client::Tick(dtime);
                server::Tick(dtime);
            }''')
        p=prepared/'src/main.cc'
        patch(p, '#include "options.hh"', '#include "options.hh"\n#include "../gameworld_bridge.hh"')
        patch(p, '            enigma::gui::ShowMainMenu();', '''            if (gw::enabled()) {
                enigma::options::SetOption("MiddleMouseButtonMode", enigma::options::MIDDLEMOUSEBUTTON_IgnoreMovement);
                SDL_WarpMouseInWindow(SDL_GetWindowFromID(1),400,260);
                enigma::game::StartGame();
            }
            else enigma::gui::ShowMainMenu();''')
        patch(p, '    enigma::Randomize(false);\n    enigma::Randomize(true);', '''    if (gw::enabled()) {
        enigma::Randomize(20260914u, false);
        enigma::Randomize(20260914u, true);
    } else {
        enigma::Randomize(false);
        enigma::Randomize(true);
    }''')
        p=prepared/'src/server.cc'
        patch(p, '#include "server.hh"', '#include "server.hh"\n#include "../gameworld_bridge.hh"')
        patch(p, 'void Msg_MouseForce(const ecl::V2 &f) {', 'void Msg_MouseForce(const ecl::V2 &f) {\n    if (gw::enabled() && gw::sequence < 0) return;')
        patch(p, 'void Msg_StartGame() {', 'void Msg_StartGame() {\n    if (gw::enabled()) gw::loaded=true;')
        patch(p, 'void RestartLevel() {', 'void RestartLevel() {\n    if (gw::enabled()) { gw::lost=true; return; }')
        patch(p, 'void Msg_RestartGame() {', 'void Msg_RestartGame() {\n    if (gw::enabled()) { gw::lost=true; return; }')
        p=prepared/'src/player.cc'
        patch(p, '#include "player.hh"', '#include "player.hh"\n#include "../gameworld_bridge.hh"')
        # Native spare lives can resurrect a marble without restarting the level.
        # Record that death for tasks whose public goal requires surviving it.
        patch(p, 'static bool resurrect_actor(unsigned pl, Actor *a) {',
              'static bool resurrect_actor(unsigned pl, Actor *a) {\n    if (gw::enabled() && !gw::won) gw::lost=true;')
        p=prepared/'src/client.cc'
        patch(p, '#include "client.hh"', '#include "client.hh"\n#include "../gameworld_bridge.hh"')
        # Native focus-loss menus stop the event loop; the benchmark already freezes time.
        text=p.read_text()
        if text.count('                show_menu(false);') != 2:
            raise RuntimeError('Enigma focus-loss hook changed')
        p.write_text(text.replace('                show_menu(false);', '                if (!gw::enabled()) show_menu(false);'))
        patch(p, 'void Client::show_menu(bool isESC) {', 'void Client::show_menu(bool isESC) {\n    if (gw::enabled()) return;')
        patch(p, 'void Msg_AdvanceLevel(lev::LevelAdvanceMode mode) {', 'void Msg_AdvanceLevel(lev::LevelAdvanceMode mode) {\n    if (gw::enabled()) return;')
        patch(p, '        client_instance.level_finished();', '        client_instance.level_finished();\n        if (gw::enabled()) gw::won=true;')
        run([cmake,'-S',str(prepared),'-B',str(output),*flags])
        run([cmake,'--build',str(output),'--target','enigma','--parallel','4'])
        return [str(output/'src/enigma'),'--window','--nograb','--log','--nosound','--robinson','--lang','en',
                '--data',str(prepared/'data'),'--pref','{private}',str(ROOT/'game_packages/enigma/levels')+'/{scenario}.xml']
    if package == 'endless_sky':
        return build_endless(prepared, output, cmake, flags)
    raise ValueError(package)


def build_endless(prepared, output, cmake, flags):
    import shutil
    for name in ['GameWorld.h','GameWorld.cpp']:
        shutil.copyfile(prepared/name, prepared/'source'/name)
    p=prepared/'source/CMakeLists.txt'
    patch(p, 'target_sources(EndlessSkyLib PRIVATE\n\tAI.cpp', 'target_sources(EndlessSkyLib PRIVATE\n    GameWorld.cpp\n    GameWorld.h\n\tAI.cpp')
    p=prepared/'source/GameLoadingPanel.cpp'
    patch(p, '#include "GameLoadingPanel.h"', '#include "GameLoadingPanel.h"\n#include "GameWorld.h"\n#include "MainPanel.h"')
    patch(p, '\t\tplayer.LoadRecent();', '\t\tif(GameWorld::Enabled()) GameWorld::Initialize(player);\n\t\telse player.LoadRecent();')
    patch(p, '\t\tif(conversation.IsEmpty())', '''        if(GameWorld::Enabled()) {
            gamePanels.Reset();
            gamePanels.CanSave(true);
            gamePanels.Push(new MainPanel(player));
            gamePanels.StepAll();
        }
        else if(conversation.IsEmpty())''')
    p=prepared/'source/main.cpp'
    patch(p, '#include "PlayerInfo.h"', '#include "PlayerInfo.h"\n#include "GameWorld.h"')
    patch(p, '\t\t\tProcessEvents();\n\n\t\t\tSDL_Keymod', '\t\t\tGameWorld::BeginFrame();\n\t\t\tProcessEvents();\n\n\t\t\tSDL_Keymod')
    patch(p, '\t\t\tAudio::Step(isFastForward);\n\n\t\t\tcpuLoadSum', '\t\t\tGameWorld::Publish(player);\n\t\t\tAudio::Step(isFastForward);\n\n\t\t\tcpuLoadSum')
    p=prepared/'source/MainPanel.cpp'
    patch(p, '#include "MainPanel.h"', '#include "MainPanel.h"\n#include "GameWorld.h"')
    patch(p, 'void MainPanel::Step()\n{\n\tengine.Wait();', '''void MainPanel::Step()
{
    engine.Wait();
    if(GameWorld::Enabled() && GameWorld::Ready() && !GameWorld::Advance()) return;''')
    # Prevent replacing the benchmark session through native load/new menu entries.
    p=prepared/'source/PlayerInfo.cpp'
    patch(p, '#include "PlayerInfo.h"', '#include "PlayerInfo.h"\n#include "GameWorld.h"')
    for signature in ['void PlayerInfo::New(const StartConditions &start, const shared_ptr<PilotProfile> &pilot)',
                      'void PlayerInfo::Load(const filesystem::path &path, const shared_ptr<PilotProfile> &pilot)']:
        patch(p, signature+'\n{', signature+'\n{\n    if(GameWorld::Enabled() && GameWorld::Ready()) { GameWorld::Violation(); return; }')
    sdk=run(['xcrun','--show-sdk-path'],capture_output=True).stdout.strip()
    (prepared/'build').mkdir(exist_ok=True)
    run([cmake,'-S',str(prepared),'-B',str(output),*flags,'-DES_USE_VCPKG=OFF','-DBUILD_TESTING=OFF',f'-DUUID_INCLUDE={sdk}/usr/include'])
    run([cmake,'--build',str(output),'--target','EndlessSky','--parallel','4'])
    return [str(output/'endless-sky'), '--resources',str(prepared),'--config','{private}']
