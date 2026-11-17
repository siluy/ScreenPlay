/* Native Enigma text view and primitive inputs. GPL-2.0-or-later.
 * This header is compiled only into the independent experimental text binary.
 */
#pragma once
#include "../../../.cache/prepared/enigma/gameworld_bridge.hh"
#include "../../../.cache/prepared/openttd/src/3rdparty/nlohmann/json.hpp"
#include "world.hh"
#include "actors.hh"
#include "stones.hh"
#include "items.hh"
#include "floors.hh"
#include "player.hh"
#include "server.hh"
#include "options.hh"
#include "Inventory.hh"
#include <SDL.h>
#include <cmath>
#include <iostream>
#include <map>
#include <sstream>

namespace gwtext {
using namespace enigma;
using json=nlohmann::json;
inline std::map<std::pair<int,int>,double> opening_since;
inline bool action_error=false;

inline std::string KeyAppearance(Object *o) {
    if(o->getAttr("invisible").toBool()) return "key shape hidden";
    int code=o->getAttr("code").toInt();
    return code>=1 && code<=8 ? "key shape " + std::to_string(code) : "key";
}

inline std::string describe() {
    if(Width()!=20 || Height()!=13) throw std::runtime_error("Unsupported visible board dimensions");
    std::ostringstream out;out.setf(std::ios::fixed);out.precision(2);
    out << "Visible board: 20 columns, 13 rows. x=0..19, y=0..12. Marble center: (" << gw::x << "," << gw::y << ").\n";
    out << "Legend: .=lawn, I=ice, ~=water, s=sand, #=plain stone (closed a-style), O=closed/opening b-style oxyd, o=revealed oxyd, B=wooden crate, D=closed door, d=open door, S=switch, K=key switch, k=key item.\n";
    std::ostringstream objects;
    for(int y=0;y<13;++y) {
        out << "y=" << y << ": ";
        for(int x=0;x<20;++x) {
            GridPos p(x,y);Floor *f=GetFloor(p);Stone *s=GetStone(p);Item *it=GetItem(p);
            std::string floor=f?f->getClass():"missing floor";
            char c=floor=="fl_lawn"?'.':floor=="fl_ice"?'I':floor=="fl_water"?'~':floor=="fl_sand"?'s':'?';
            if(it && it->getClass()=="it_key") {
                c='k';objects << "(" << x << "," << y << ") " << KeyAppearance(it) << ".\n";
            }
            if(s) {
                std::string kind=s->getClass();
                if(kind=="st_oxyd") {
                    int state=s->getAttr("state").toInt();
                    auto key=std::make_pair(x,y);
                    if(state==0) opening_since.erase(key);
                    else if(!opening_since.count(key)) opening_since[key]=server::LevelTime;
                    bool revealed=state>0 && server::LevelTime-opening_since[key]>=.5;
                    c=revealed?'o':'O';
                    objects << "(" << x << "," << y << ") oxyd: ";
                    if(revealed) objects << "color " << s->getAttr("oxydcolor").toInt() << (state==2?"; paired":"; open");
                    else objects << "color hidden";
                    objects << ".\n";
                } else if(kind=="st_door") {
                    c=s->getAttr("state").toInt()?'d':'D';
                    objects << "(" << x << "," << y << ") door " << (s->getAttr("state").toInt()?"open":"closed or transitioning") << ".\n";
                } else if(kind=="st_switch") {
                    c='S';objects << "(" << x << "," << y << ") switch " << (s->getAttr("state").toInt()?"on":"off") << ".\n";
                } else if(kind=="st_key") {
                    c='K';objects << "(" << x << "," << y << ") key switch: " << KeyAppearance(s) << "; " << (s->getAttr("state").toInt()?"on":"off") << ".\n";
                } else if(kind=="st_box") c='B';
                else c='#';
            }
            out << c;
        }
        out << "\n";
    }
    out << objects.str();
    out << "Inventory (first item activates): ";
    Inventory *inv=player::GetInventory(0);
    if(!inv || inv->size()==0) out << "empty";
    else for(size_t i=0;i<inv->size();++i) {
        Item *it=inv->get_item(i);
        out << (i?", ":"") << i+1 << ": " << (it->getClass()=="it_key"?KeyAppearance(it):it->getClass());
    }
    out << ".\nMouse sensitivity: " << options::GetDouble("MouseSpeed") << ".\n";
    return out.str();
}

inline void input(const json &action) {
    const std::string kind=action.at("type");
    if(kind=="wait") return;
    if(kind=="push") {
        int dx=action.at("dx"),dy=action.at("dy");
        if(abs(dx)>300 || abs(dy)>300) throw std::runtime_error("Impulse out of range");
        server::Msg_MouseForce(options::GetDouble("MouseSpeed")*ecl::V2(dx,dy));
    } else if(kind=="activate_item") server::Msg_ActivateItem();
    else if(kind=="rotate_inventory") player::RotateInventory(+1);
    else throw std::runtime_error("Unavailable action");
}

inline void publish() {
    if(!gw::ready) return;
    // Track visible opening transitions on every native update, not only at observations.
    for(int y=0;y<Height();++y) for(int x=0;x<Width();++x) {
        Stone *s=GetStone(GridPos(x,y));
        if(s && s->getClass()=="st_oxyd") {
            auto key=std::make_pair(x,y);
            if(!s->getAttr("state").toInt()) opening_since.erase(key);
            else if(!opening_since.count(key)) opening_since[key]=server::LevelTime;
        }
    }
    if(gw::processed<gw::target) return;
    std::ifstream file(std::getenv("GAMEWORLD_STATE_FILE"));json state;file>>state;
    state["text"]=describe();state["action_error"]=action_error;
    std::cout << "GWSTATE " << state.dump() << std::endl;
    std::string line;
    if(!std::getline(std::cin,line)) std::exit(0);
    json request=json::parse(line);
    int sequence=request.at("sequence"),updates=request.at("updates");
    if(sequence<=gw::sequence || updates<0 || updates>500) throw std::runtime_error("Invalid trusted envelope");
    gw::sequence=sequence;gw::target=gw::processed+updates;
    std::ofstream control(std::getenv("GAMEWORLD_CONTROL_FILE"));
    control << gw::sequence << ' ' << gw::target << '\n';control.close();
    action_error=false;
    try {input(request.at("action"));}
    catch(const std::exception &) {action_error=true;}
}
}
