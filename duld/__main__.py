import sys

from .util import Shell


main = Shell(sys.argv)
exit_code = main()
sys.exit(exit_code)
