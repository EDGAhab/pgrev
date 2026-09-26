# Dump special-net geometry: net, shape, layer, x1 y1 x2 y2 [, via info]
# Usage: ODB_IN=<odb> CSV_OUT=<csv> openroad -exit src/dump_pg.tcl
read_db $::env(ODB_IN)
set block [ord::get_db_block]
set out [open $::env(CSV_OUT) w]
puts $out "net,shape,layer,x1,y1,x2,y2,via_name,via_bot,via_top"
foreach net [$block getNets] {
    set st [$net getSigType]
    if {$st != "POWER" && $st != "GROUND"} continue
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
                # via layer from via def if possible; else leave blank
            } else {
                if {![catch {set tl [$b getTechLayer]}] && $tl != "" && $tl != "NULL"} {
                    catch {set layer [$tl getName]}
                }
            }
            puts $out "$nm,$shape,$layer,$x1,$y1,$x2,$y2,$vn,$vb,$vt"
        }
    }
}
close $out
puts "wrote $::env(CSV_OUT)"
