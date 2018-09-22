#!/bin/bash
# Purpose: release script for braiins OS firmware

# The script:
# - runs a build of braiins-os for all specified targets
# - and generates scripts for packaging and signing the resulting build of
#
#
# Synopsis: ./build-release.sh KEYRINGSECRET RELEASE SUBTARGET1 [SUBTARGET2 [SUBTARGET3...]]
set -e
#
parallel_jobs=32
# default target is zynq
target=zynq
git_repo=git@gitlab.bo:x/braiins-os

key=`realpath $1`
shift
date_and_patch_level=$1
shift
release_subtargets=$@

#DRY_RUN=echo
STAGE1=y
CLONE=y

echo ID is: `id`
echo KEY is: $key
echo RELEASE_BUILD_DIR is: $RELEASE_BUILD_DIR
echo DATE and PATCH LEVEL: $date_and_patch_level
echo RELEASE SUBTARGETS: $release_subtargets

$DRY_RUN mkdir -p $RELEASE_BUILD_DIR
$DRY_RUN cd $RELEASE_BUILD_DIR

if [ $CLONE = y ]; then
    $DRY_RUN git clone $git_repo
fi

# Prepare build environment
$DRY_RUN cd braiins-os
if [ $STAGE1 = y ]; then
    $DRY_RUN virtualenv --python=/usr/bin/python3.5 .env
fi
$DRY_RUN source .env/bin/activate
$DRY_RUN pip3 install -r requirements.txt


function generate_sd_img() {
    sd_img=$1/sd.img
    echo dd if=/dev/zero of=$sd_img bs=1M count=32
    echo parted ./$sd_img --script mktable msdos
    echo parted ./$sd_img --script mkpart primary fat32 2048s 16M
    echo parted ./$sd_img --script mkpart primary ext4 16M 32M

    echo sudo kpartx -s -av ./$sd_img
    echo sudo mkfs.vfat /dev/mapper/loop0p1
    echo sudo mount /dev/mapper/loop0p1 /mnt
    echo sudo cp $1/'sd/*' /mnt/
    echo sudo umount /mnt
    echo sudo kpartx -d ./$sd_img
}

# Iterate all releases/switch repo and build
for subtarget in $release_subtargets; do
    # latest release
    tag=`git tag | grep $subtarget | grep $date_and_patch_level | tail -1`
    platform=$target-$subtarget
    fw_prefix=braiins-os-$tag
    case $subtarget in
	am*) nand=am;;
	dm*) nand=dm_v2;;
	*) echo Unrecognized subtarget: $subtarget; exit 2;;
    esac
    $DRY_RUN git checkout $tag
    # We need to ensure that feeds are update
    if [ $STAGE1 = y ]; then
	$DRY_RUN ./bb.py --platform $platform prepare
	$DRY_RUN ./bb.py --platform $platform prepare --update-feeds
    fi
    # build everything for a particular platform
    $DRY_RUN ./bb.py --platform $platform build --key $key -j$parallel_jobs -v

    # Deploy SD and NAND images
    for i in sd nand_$nand; do
	$DRY_RUN ./bb.py --platform $platform deploy local_$i --pool-user !non-existent-user!
    done

    # Feeds deploy is specially handled as it has to merge with firmware packages
    output_dir=output
    publish_dir=$output_dir/publish/$subtarget
    packages=$publish_dir/Packages
    if [ -f $packages ]; then
	echo Detected existing publish directory for $platform merging Packages...
	extra_feeds_opts="--feeds-base $packages"
    else
	echo Nothing has been published for $platform, skipping merge of Packages...
	extra_feeds_opts=
    fi
    $DRY_RUN ./bb.py --platform $platform deploy local_feeds $extra_feeds_opts --pool-user !non-existent-user!

    # Make local adjustments to directory structure
    ($DRY_RUN cd $output_dir;
     factory_fw=factory_transition;
     $DRY_RUN mv $platform $fw_prefix;
     ($DRY_RUN cd $fw_prefix;
      $DRY_RUN mv nand_$nand $factory_fw;
      ($DRY_RUN cd $factory_fw;
       $DRY_RUN mv upgrade.py upgrade2bos.py;
       $DRY_RUN mv restore.py restore2factory.py
      )
     )
     pack_and_sign_script=pack-and-sign-$fw_prefix.sh
     fw_archive=$fw_prefix.tar.bz2
     generate_sd_img $fw_prefix > $pack_and_sign_script;
     echo tar cvjf $fw_archive $fw_prefix --exclude feeds --exclude sd >> $pack_and_sign_script
     echo gpg2 --armor --detach-sign --sign-with release@braiins.cz --sign ./$fw_archive >> $pack_and_sign_script
     echo mkdir -p publish/$subtarget >> $pack_and_sign_script
     echo cp $fw_prefix/feeds/\* publish/$subtarget >> $pack_and_sign_script
     echo mv $fw_archive* publish >> $pack_and_sign_script
    )


done
