# Dump ALL nets' swire geometry (wires + vias) as flat boxes.
# This is the geometry source for the GDSII stream-out (expB, rev5).
# Unlike dump_pg.tcl, no POWER/GROUND filter: a foundry GDSII contains
# every net's routed geometry. (At the 2_6_floorplan_pdn stage only the
# PDN nets have routed boxes; signal nets are unrouted.)
# Usage: ODB_IN=<odb> CSV_OUT=<csv> openroad -exit src/dump_all_geo.tcl
read_db $::env(ODB_IN)
set block [ord::get_db_block]
set out [open $::env(CSV_OUT) w]
puts $out "net,shape,layer,x1,y1,x2,y2,via_name,via_bot,via_top,sigtype"
foreach net [$block getNets] {
    set st [$net getSigType]
    set nm [$net getName]
    foreach sw [$net getSWires] {
        foreach b [$sw getWires] {
            set shape [$b getWireShapeType]
            set x1 [$b xMin]; set y1 [$b yMin]
            set x2 [$b xMax]; set y2 [$b yMax]
            set layer ""; set vn ""; set vb ""; set vt ""
            if {[$b isVia]} {
                set v ""
                if {[catch {set v [$b getTechVia]}]} {set v ""}
                if {$v == "" || $v == "NULL"} {
                    if {![catch {set v [$b getBlockVia]}]} {} else {set v ""}
                }
                if {$v != "" && $v != "NULL"} {
                    catch {set vn [$v getName]}; catch {set vb [[$v getBottomLayer] getName]}
                    catch {set vt [[$v getTopLayer] getName]}
                }
            } else {
                if {![catch {set tl [$b getTechLayer]}] && $tl != "" && $tl != "NULL"} {
                    catch {set layer [$tl getName]}
                }
            }
            puts $out "$nm,$shape,$layer,$x1,$y1,$x2,$y2,$vn,$vb,$vt,$st"
        }
    }
}
close $out
puts "wrote $::env(CSV_OUT)"
