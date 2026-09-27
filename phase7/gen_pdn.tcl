# Phase 7: generate sky130hd/gcd PDN with the CURRENT C++ pdn API.
# Legacy truth config equivalent:
#   rails { met1 {width 0.48} }, straps met4 {w1.6 p27.14 o13.57},
#   met5 {w1.6 p27.2 o13.6}, connect {{met1 met4} {met4 met5}}, starts_with POWER.
#
# Usage:  OPENROAD_EXE=<new openroad> openroad -exit gen_pdn.tcl
# Env:    TLEF, TECH_LEF, DEF_IN, ODB_OUT
set tlef $::env(TLEF)
set tech_lef $::env(TECH_LEF)
set def_in $::env(DEF_IN)
set odb_out $::env(ODB_OUT)

read_lef $tlef
read_lef $tech_lef
read_def $def_in

add_global_connection -net VDD -pin_pattern VPWR -power
add_global_connection -net VDD -pin_pattern VPB -power
add_global_connection -net VSS -pin_pattern VGND -ground
add_global_connection -net VSS -pin_pattern VNB -ground

set_voltage_domain -power VDD -ground VSS

define_pdn_grid -name grid -starts_with POWER -voltage_domains {CORE} -pins "met4 met5"

add_pdn_stripe -grid grid -layer met4 -width 1.6 -pitch 27.14 -offset 13.57 -starts_with POWER
add_pdn_stripe -grid grid -layer met5 -width 1.6 -pitch 27.2 -offset 13.6 -starts_with POWER
add_pdn_connect -grid grid -layers "met4 met5"

add_pdn_stripe -grid grid -layer met1 -width 0.48 -followpins
add_pdn_connect -grid grid -layers "met1 met4"

pdngen

write_db $odb_out
puts "wrote $odb_out"
