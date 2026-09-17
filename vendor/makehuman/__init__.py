# seam_avatar vendor package for MakeHuman core modules.
#
# Exposes the two modules used by the headless deformation pipeline:
#   - algos3d:       morph target loading and application
#   - humanmodifier: modifier-to-target weight resolution
#
# All GUI-coupled MakeHuman modules (log, getpath, guicommon, events3d, core)
# are replaced by headless stubs defined in this package. Python's import
# system finds this package first because the caller adds vendor/makehuman/
# (or vendor/) to sys.path.
