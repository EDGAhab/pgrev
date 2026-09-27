# rev4-exp2: re-run pdngen with the RECOVERED spec on the new floorplan
# (pre-PDN DEF + inserted fake macro). Usage:
#   openroad -exit run_pdn_newfloor.tcl   (with env.sh sourced)
set PDK ~/pgrev/tools/OpenROAD-flow-scripts/flow/platforms/sky130hd/lef
read_lef $PDK/sky130_fd_sc_hd.tlef
read_lef $PDK/sky130_fd_sc_hd_merged.lef
read_lef /tmp/rev4/exp2/fake_macro.lef
read_def /tmp/rev4/exp2/floorplan_macro.def
source /tmp/rev4/exp2/pdn_newfloor.cfg
pdngen -verbose
write_db /tmp/rev4/exp2/pdn_macro.odb
write_def /tmp/rev4/exp2/pdn_macro_out.def
puts "PDN_NEWFLOOR_DONE"
