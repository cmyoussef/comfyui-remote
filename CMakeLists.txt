find_package(DNeg)
find_package(DNegNuke)

project(dneg-nuke-remote)

file(GLOB_RECURSE JSON "*.json")
install(FILES ${JSON} DESTINATION lib/nuke)

file(GLOB_RECURSE TCL "*.tcl")
install(FILES ${TCL} DESTINATION lib/nuke)

file(GLOB_RECURSE PNG "*.png")
install(FILES ${PNG} DESTINATION lib/nuke)

install(FILES VERSION DESTINATION lib/python/nuke_remote)

