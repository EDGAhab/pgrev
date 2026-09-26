# Export DEF from an ODB database.
# Usage: ODB_IN=<in.odb> DEF_OUT=<out.def> openroad -exit src/export_def.tcl
read_db $::env(ODB_IN)
write_def $::env(DEF_OUT)
puts "wrote $::env(DEF_OUT)"
