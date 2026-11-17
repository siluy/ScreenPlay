/* Experimental restricted text panels. GPL-2.0, matching OpenTTD.
 * Included after the existing fixture/evaluator bridge, in its own binary.
 * Native commands enforce costs, company ownership, tile legality and orders.
 */
#include "signs_base.h"
#include "roadveh_cmd.h"
#include "vehiclelist.h"
#include <iostream>
#include <sstream>

namespace {
std::string text_panel="vehicle", road_tool;
int map_x=25, map_y=32, selected_order=-1;
bool go_to=false, action_error=false;
void TextRequire(bool ok) { if(!ok) throw std::runtime_error("Native command rejected"); }

bool InTextView(int x, int y) {
    return x>=1 && x<=62 && y>=1 && y<=62 && abs(x-map_x)<=12 && abs(y-map_y)<=6;
}
std::string StationName(StationID id) {
    if(id==west) return "West Stop";
    if(id==east) return "East Stop";
    if(id==central) return "Central Stop";
    return "Station " + std::to_string(id.base());
}
std::string DescribeText() {
    std::ostringstream out;
    const Vehicle *v=Vehicle::GetIfValid(bus_id);
    const Company *c=Company::GetIfValid(_local_company);
    out << "Current panel: " << text_panel << ". Cash: " << (c ? int64_t(c->money) : 0) << " GBP.\n";
    out << "Panels: map, vehicle, orders, road.\n";
    if(text_panel=="vehicle" && v) {
        out << "Inspection Bus: " << (v->vehstatus.Test(VehState::Stopped)?"stopped":"running")
            << "; " << (v->IsInDepot()?"inside depot":"outside depot")
            << "; tile (" << TileX(v->tile) << "," << TileY(v->tile) << ").\n";
        out << "Controls: start_stop, send_to_depot, turn_around.\n";
        if(v->current_order.IsType(OT_LOADING)) out << "Currently loading at " << StationName(v->last_station_visited) << ".\n";
    }
    if(text_panel=="orders" && v) {
        for(int i=0;i<v->GetNumOrders();++i) {
            const Order *o=v->GetOrder(i);
            out << "Order " << i+1 << (i==selected_order?" [selected]":"") << ": ";
            if(o->IsType(OT_GOTO_STATION) || o->IsType(OT_IMPLICIT)) {
                out << StationName(StationID(o->GetDestination().base()))
                    << (o->IsType(OT_IMPLICIT)?"; implicit":"; explicit")
                    << (o->GetLoadType()==OrderLoadType::LoadIfPossible?"; load if available":"; full load or other loading policy");
            } else out << "other native order";
            out << "\n";
        }
        out << "Order " << v->GetNumOrders()+1 << (selected_order==v->GetNumOrders()?" [selected]":"") << ": END (append here).\n";
        out << "Controls: go_to, delete_order, toggle_full_load, skip_order.\nPlacement mode: " << (go_to?"go_to: click a station":"none") << ".\n";
    }
    if(text_panel=="road") out << "Road controls: build_x, build_y, remove_x, remove_y. Selected tool: " << (road_tool.empty()?"none":road_tool) << ".\n";
    if(text_panel=="map" || text_panel=="road" || (text_panel=="orders" && go_to)) {
        out << "Map view center (" << map_x << "," << map_y << "). x increases across rows; y increases down rows.\n";
        out << "Legend: .=clear terrain, ~=water, T=trees, -=road X, |=road Y, +=junction, S=bus stop, D=road depot, #=building, ?=other terrain. Road exits below use x-/x+/y-/y+.\n";
        for(int y=std::max(1,map_y-6);y<=std::min(62,map_y+6);++y) {
            out << "y=" << y << " x=" << std::max(1,map_x-12) << ".." << std::min(62,map_x+12) << ": ";
            for(int x=std::max(1,map_x-12);x<=std::min(62,map_x+12);++x) {
                TileIndex tile=TileXY(x,y);
                RoadBits bits=GetAnyRoadBits(tile,RTT_ROAD);
                char ch=IsTileType(tile,MP_CLEAR)?'.':IsTileType(tile,MP_WATER)?'~':IsTileType(tile,MP_TREES)?'T':'?';
                if(bits!=ROAD_NONE) ch=bits==ROAD_X?'-':bits==ROAD_Y?'|':'+';
                if(IsTileType(tile,MP_HOUSE)) ch='#';
                if(IsStationRoadStopTile(tile)) ch='S';
                if(IsRoadDepotTile(tile)) ch='D';
                out << ch;
            }
            out << "\n";
        }
        for(int y=std::max(1,map_y-6);y<=std::min(62,map_y+6);++y) for(int x=std::max(1,map_x-12);x<=std::min(62,map_x+12);++x) {
            TileIndex tile=TileXY(x,y);RoadBits bits=GetAnyRoadBits(tile,RTT_ROAD);
            if(bits!=ROAD_NONE) {
                out << "(" << x << "," << y << ") exits:";
                if(bits & ROAD_NE) out << " x-";
                if(bits & ROAD_SW) out << " x+";
                if(bits & ROAD_NW) out << " y-";
                if(bits & ROAD_SE) out << " y+";
                if(IsStationRoadStopTile(tile)) out << "; " << StationName(GetStationIndex(tile));
                if(IsRoadDepotTile(tile)) out << "; depot";
                out << ".\n";
            }
        }
        for(const Sign *s:Sign::Iterate()) if(InTextView(s->x/TILE_SIZE,s->y/TILE_SIZE))
            out << "Sign (" << s->x/TILE_SIZE << "," << s->y/TILE_SIZE << "): " << s->name << ".\n";
        if(v && !v->IsInDepot() && InTextView(TileX(v->tile),TileY(v->tile)))
            out << "Inspection Bus visible at (" << TileX(v->tile) << "," << TileY(v->tile) << ").\n";
    }
    return out.str();
}

void TextAction(const nlohmann::json &a) {
    const std::string kind=a.at("type");
    Vehicle *v=Vehicle::GetIfValid(bus_id);
    if(!v) throw std::runtime_error("No bus");
    _current_company=_local_company;
    if(kind=="wait") return;
    if(kind=="open_panel") {
        text_panel=a.at("panel");go_to=false;road_tool.clear();selected_order=-1;return;
    }
    if(kind=="pan_map") {map_x=a.at("x");map_y=a.at("y");return;}
    if(kind=="select_order" && text_panel=="orders") {
        int i=a.at("index");
        if(i<1 || i>v->GetNumOrders()+1) throw std::runtime_error("Order outside list");
        selected_order=i-1;go_to=false;return;
    }
    if(kind=="click") {
        std::string control=a.at("control");
        if(text_panel=="vehicle") {
            if(control=="start_stop") TextRequire(Command<CMD_START_STOP_VEHICLE>::Post(v->tile,bus_id,true));
            else if(control=="send_to_depot") TextRequire(Command<CMD_SEND_VEHICLE_TO_DEPOT>::Post(bus_id,DepotCommandFlags{},VehicleListIdentifier{}));
            else if(control=="turn_around") TextRequire(Command<CMD_TURN_ROADVEH>::Post(v->tile,bus_id));
            else throw std::runtime_error("Wrong panel control");
            return;
        }
        if(text_panel=="road" && (control=="build_x" || control=="build_y" || control=="remove_x" || control=="remove_y")) {road_tool=control;return;}
        if(text_panel=="orders") {
            if(control=="go_to") {go_to=!go_to;return;}
            if(control=="skip_order") {
                TextRequire(Command<CMD_SKIP_TO_ORDER>::Post(v->tile,bus_id,static_cast<VehicleOrderID>((v->cur_implicit_order_index+1)%std::max(1,int(v->GetNumOrders())))));return;
            }
            if(selected_order<0 || selected_order>=v->GetNumOrders()) throw std::runtime_error("Select an order");
            if(control=="delete_order") {
                TextRequire(Command<CMD_DELETE_ORDER>::Post(v->tile,bus_id,static_cast<VehicleOrderID>(selected_order)));
                if(selected_order>=v->GetNumOrders()) selected_order=v->GetNumOrders();
            } else if(control=="toggle_full_load") {
                auto mode=v->GetOrder(selected_order)->GetLoadType()==OrderLoadType::LoadIfPossible?OrderLoadType::FullLoadAny:OrderLoadType::LoadIfPossible;
                TextRequire(Command<CMD_MODIFY_ORDER>::Post(v->tile,bus_id,static_cast<VehicleOrderID>(selected_order),MOF_LOAD,to_underlying(mode)));
            } else throw std::runtime_error("Wrong orders control");
            return;
        }
    }
    if(kind=="click_tile" && text_panel=="orders" && go_to) {
        int x=a.at("x"),y=a.at("y");
        if(!InTextView(x,y)) throw std::runtime_error("Outside view");
        TileIndex tile=TileXY(x,y);
        if(!IsStationRoadStopTile(tile)) throw std::runtime_error("Not a stop");
        Order order;order.MakeGoToStation(GetStationIndex(tile));order.SetStopLocation(OrderStopLocation::FarEnd);
        int insert=selected_order>=0?selected_order:v->GetNumOrders();
        TextRequire(Command<CMD_INSERT_ORDER>::Post(v->tile,bus_id,static_cast<VehicleOrderID>(insert),order));
        selected_order=insert+1;return;
    }
    if(kind=="draw_road" && text_panel=="road" && !road_tool.empty()) {
        int x1=a.at("x1"),y1=a.at("y1"),x2=a.at("x2"),y2=a.at("y2");
        if(!InTextView(x1,y1) || !InTextView(x2,y2)) throw std::runtime_error("Outside view");
        Axis axis=road_tool.back()=='x'?AXIS_X:AXIS_Y;
        if((axis==AXIS_X && y1!=y2) || (axis==AXIS_Y && x1!=x2)) throw std::runtime_error("Tool alignment");
        TileIndex start=TileXY(std::min(x1,x2),std::min(y1,y2)),end=TileXY(std::max(x1,x2),std::max(y1,y2));
        if(road_tool.rfind("build",0)==0)
            TextRequire(Command<CMD_BUILD_LONG_ROAD>::Post(end,start,ROADTYPE_ROAD,axis,DRD_NONE,false,true,false));
        else TextRequire(Command<CMD_REMOVE_LONG_ROAD>::Post(end,start,ROADTYPE_ROAD,axis,false,true));
        return;
    }
    throw std::runtime_error("Unavailable action");
}
}

static void TextPublish(nlohmann::json &j) {
    if(!ready || !error.empty() || updates<target_updates) return;
    j["text"]=DescribeText();j["action_error"]=action_error;
    // Persist the exact response before blocking for the next decision.
    const std::string state_path=getenv("GAMEWORLD_STATE_FILE"), temp=state_path+".text.tmp";
    { std::ofstream file(temp); file << j.dump(); }
    std::filesystem::rename(temp,state_path);
    std::cout << "GWSTATE " << j.dump() << std::endl;
    std::string line;
    if(!std::getline(std::cin,line)) std::exit(0);
    const auto request=nlohmann::json::parse(line);
    const uint64_t seq=request.at("sequence"), count=request.at("updates");
    if(seq<=control_sequence || count>167) throw std::runtime_error("Invalid trusted envelope");
    control_sequence=seq;target_updates=updates+count;action_error=false;
    try { TextAction(request.at("action")); }
    catch(const std::exception &) {action_error=true;target_updates=updates;}
}
