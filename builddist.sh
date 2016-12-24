#!/bin/sh

# Build OpenERP 7.0 and 8.0 sdists.
#
# You MUST place this in the root of your odoo repository.  It expects you
# have the local branches 7.0 and any other you may use.
#
# Usage:
#
#    ./builddist.sh [--no-pep440] [BRANCH] [VERSION]
#
# The default for BRANCH is "7.0".  If BRANCH is set but VERSION is not, it
# defaults to the part of BRANCH after the first "-" which starts with a
# digit.
#

# Copyright (c) 2014, 2015 Merchise Autrement and Contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.


# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.


if [ "$1" = "--no-pep440" ]; then
    USEPEP440=""
    shift
else
    USEPEP440="1"
fi

if [ -z "$1" ]; then
    BRANCH=`git branch | grep ^* | cut -b3-`
else
    BRANCH="$1"
fi


if [ -z "$2" ]; then
    VERSION=`python -c "import re; \
                P=re.compile(r'-(\d[\d\.]+.*)$'); \
                P2=re.compile(r'(\d[\d\.]+.*)$'); \
                match=P.search('$BRANCH') or P2.search('$BRANCH'); \
                print(match.groups()[-1] if match else '')"`
    if [ -z "$VERSION" ]; then
	echo "ERROR:  Impossible to detect the version from branch '$BRANCH'" >&2
	echo "Either use a branch with a trailing '-VERSION' or pass the"\
             "VERSION argument" >&2
	exit 1
    fi
else
    VERSION="$2"
fi


if [ "$VERSION" = "7.0" ]; then
    DISTRIBUTION='openerp'
else
    # Now 8.0 is odoo
    DISTRIBUTION='odoo'
fi


# Save the liver...
CWD=`pwd`
if [ ! -f ./openerp-server ]; then
    cd `dirname $0`
fi

RELEASE=`git log $BRANCH -1 --pretty=%h`
COMMITER_DATE=`git log $BRANCH -1 --pretty=%cd --date=iso`
if [ -z $USEPEP440 ]; then
    STAMP=`date --date="$COMMITER_DATE" +"%Y%m%d-%H%M%S"`
else
    STAMP=`date --date="$COMMITER_DATE" +"%Y%m%d.%H%M%S"`
fi

TMPDIR=`python -c "import tempfile; print tempfile.mkdtemp(prefix='odoo-')"`
mkdir "$TMPDIR/src"
mkdir "$TMPDIR/pkg"
git archive $BRANCH > "$TMPDIR/src/openerp.tar"
cd "$TMPDIR/src"
tar -xf openerp.tar

# Need to dist the addons
mv addons/* openerp/addons/

# Rewrite the version
if [ -z $USEPEP440 ]; then
    sed -i "s/FINAL, STAMP/FINAL, \"-$STAMP-$RELEASE\"/" openerp/release.py
    sed -i "s/, ALPHA,[^)]*/, ALPHA, '-$STAMP-$RELEASE'/" openerp/release.py
else
    sed -i "s/FINAL, STAMP/FINAL, \".$STAMP+$RELEASE\"/" openerp/release.py
    sed -i "s/, ALPHA,[^)]*/, ALPHA, '.$STAMP+$RELEASE'/" openerp/release.py
fi

python setup.py --quiet sdist -d "$TMPDIR/pkg"

#  Detect the true name
VERSION_STAMP=`grep "^Version: " "$DISTRIBUTION".egg-info/PKG-INFO | cut -b10-`
PKGNAME="$DISTRIBUTION-$VERSION_STAMP"
PKG="$PKGNAME.tar.gz"


# The following incantation is to avoid a directory not found in Odoo v8.
cd "$TMPDIR/pkg"
gunzip "$PKG"
mkdir -p "$PKGNAME/addons/"
echo "#" > "$PKGNAME/addons/__dummy__.py"
tar -f "$PKGNAME.tar" -r "$PKGNAME/addons/__dummy__.py"
gzip "$PKGNAME.tar"

# Clean up
mv "$TMPDIR/pkg/$PKG" "$CWD/"
rm -rf "$TMPDIR"
cd "$CWD"

echo "Built $PKG"
