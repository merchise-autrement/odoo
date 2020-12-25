#!/bin/bash
#
# Usage: ../runtests.sh [-i addons] [-s|--no-capture] [-- paths-to-install-with-pip]
#
# This should be run inside an Odoo worktree.
#
# If a virtualenv is active it will use it unchanged.  Otherwise, it creates a
# new virtualenv, install the current Odoo tree, and the
# path-to-install-with-pip.
#
# Options:
#
#   `-i ADDONS`              Addons to test separated by commas.
#
#   `-s` (`--no-capture`)    Don't capture the output.  This allows to trace
#                            with pdb.
#
#   `-p PYTHON`              Use a given Python interpreter.  Otherwise, guess.
#
#   `-exec EXEC`             Use EXEC to run the tests.
#
#   `--no-venv`              Don't create a virtualenv.

# The name of the DB is built from the name of the addon but it's hashed to
# avoid clashes in a shared DB env with a CI server not running in a
# container.

# Allow debuging this shell script
if [ ! -z $TRACE ]; then
    set -x
fi

NOW=`date +%s`
CDIR=`pwd`
HASH=`echo "$CDIR-$NOW" | md5sum -t - | awk '{print $1}' |cut -b-9`
DB=tdb_"$HASH"
STDOUT="/tmp/odoo-$HASH.log"

echo "Logs in $STDOUT"

ARGS=''
ADDONS=''
EXEC=''
collecting=''

function psql_wrapper() {
    cmd="$(which ${FUNCNAME[1]}) "
    if [ ! -z $POSTGRES_HOST ];then
        cmd="$cmd -h $POSTGRES_HOST"
    fi
    if [ ! -z $POSTGRES_USER ];then
        cmd="$cmd -U$POSTGRES_USER"
    fi
    echo $cmd $@
}

if [ ! -z $POSTGRES_PASSWORD ];then
    export PGPASSWORD=$POSTGRES_PASSWORD;
fi

function dropdb() { `psql_wrapper $@`; }
function createdb() { `psql_wrapper $@`; }
function psql() { `psql_wrapper $@`; }

while [ \! -z "$1" ]; do
    case $1 in
        -p)
            shift
            if [ -z "$1" ]; then
                echo "-p requires an argument"
                exit 1;
            else
                python="$1"
            fi
            ;;
        --no-venv)
            # Trick me to use no virtual env.
            VIRTUAL_ENV='fake'
            ;;
        -exec)
            shift
            if [ -z "$1" ]; then
                echo "-exec requires an argument"
                exit 1;
            else
                EXEC="$1"
            fi
            ;;
        -i)
            shift
            if [ -z "$1" ]; then
                echo "-i requires an argument"
                exit 1;
            else
                ADDONS="$1"
            fi
            ;;
        -s)
            STDOUT=''
            ;;
        --no-capture)
            STDOUT=''
            ;;
        --)
            shift
            paths="$*"
            while [ \! -z "$1" ]; do
                shift
            done
            ;;
        *)
            ARGS="$ARGS $1"
            ;;
    esac
    shift
done

if [ -z $VIRTUAL_ENV ]; then
    VENV=/tmp/venv_"$HASH"
    NEW_VENV='yes'
else
    VENV="$VIRTUAL_ENV"
    NEW_VENV=''
fi

if [ -z "$EXECUTABLE" ]; then
    EXECUTABLE="$EXEC"
fi
if [ -z "$EXECUTABLE" ]; then
    EXECUTABLE="./odoo-bin"
fi

if [ -z $VIRTUAL_ENV ]; then
    if [ -z "$python" ]; then
        python=`which python3`
    fi
    echo "Creating virtualenv $VENV ($python) and installing the packages.  Wait for it."
    virtualenv -p $python $VENV &&
        trap 'rm -rf $VENV; dropdb $DB; exit $CODE ' EXIT && \
        trap 'rm -rf $VENV; dropdb $DB; rm -f -- $STDOUT; exit 13' TERM INT KILL

    echo "Not done yet..."
    source $VENV/bin/activate
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
    pip install -e .
    pip install websocket-client "ipython<6" ipdb "hypothesis>=3.24" "phonenumbers~=8.12"
    if [ \! -z "$paths" ]; then
        echo Installing $paths
        for repo in $paths; do pip install -e $repo; done
    fi
fi

echo "Logs in $STDOUT"

# Just in case
dropdb $DB 2>/dev/null

ARGS="$ARGS --stop-after-init --test-enable --log-level=test --workers=0 --max-cron-threads=0"
if [ -z "$ADDONS" ]; then
    # XXX: Putting -i all does not work.  I have to look in standard addons
    # places.  However, I omit hardware-related addons.
    ADDONS=`ls addons | grep -v ^hw| xargs | tr " " ","`
    ADDONS="$ADDONS,`ls openerp/addons | xargs | tr " " ","`"
fi
ARGS="$ARGS -i $ADDONS"

echo running $EXECUTABLE -d $DB $ARGS


# Create the DB install the addons and run tests.
if [ \! -z "$STDOUT" ]; then
    createdb -E UTF-8 --template=template0 "$DB" && \
	        echo 'CREATE EXTENSION postgis' | psql -d "$DB" && \
	        echo 'CREATE TEXT SEARCH CONFIGURATION fr ( COPY = french );' | psql -d "$DB" && \
        trap 'test \! -z $NEW_VENV && rm -rf $VENV; dropdb $DB; exit $CODE ' EXIT && \
        trap 'test \! -z $NEW_VENV && rm -rf $VENV; dropdb $DB; rm -f -- $STDOUT; exit 13' TERM INT KILL && \
        $EXECUTABLE -d $DB --db-filter=^$DB\$ $ARGS 2>&1 | tee $STDOUT
else
    createdb -E UTF-8 --template=template0 "$DB" && \
	        echo 'CREATE EXTENSION postgis' | psql -d "$DB" && \
		echo 'CREATE TEXT SEARCH CONFIGURATION fr ( COPY = french );' | psql -d "$DB" && \
        trap 'test \! -z $NEW_VENV && rm -rf $VENV; dropdb $DB; exit $CODE ' EXIT && \
        trap 'test \! -z $NEW_VENV && rm -rf $VENV; dropdb $DB; rm -f -- $STDOUT; exit 13' TERM INT KILL && \
        $EXECUTABLE -d $DB --db-filter=^$DB\$ $ARGS
fi

egrep "(At least one test failed when loading the modules.|(ERROR|CRITICAL) $DB|WARNING $DB odoo.tools.view_validation: Invalid XML|WARNING $DB.*demo data failed to install|WARNING $DB odoo.schema: .* unable to add constraint)" $STDOUT
code=$?
if (($code == 0 || $code == 2)); then
    CODE=1
else
    CODE=0
fi

exit $CODE
