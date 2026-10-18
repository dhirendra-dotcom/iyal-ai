// Arthistics V0.1 parametric utensil-grip sleeve.
// All numeric dimensions are millimeters.

profile = is_undef(profile) ? "oval" : profile;
outer_width = is_undef(outer_width) ? 26 : outer_width;
outer_depth = is_undef(outer_depth) ? 20 : outer_depth;
grip_length = is_undef(grip_length) ? 82 : grip_length;
inner_width = is_undef(inner_width) ? 12 : inner_width;
inner_depth = is_undef(inner_depth) ? 5 : inner_depth;
path_shift = is_undef(path_shift) ? 0 : path_shift;
ribbed = is_undef(ribbed) ? true : ribbed;
palm_support = is_undef(palm_support) ? false : palm_support;

$fn = 72;

module oval_disc(width, depth, height=1) {
    scale([width/2, depth/2, 1]) cylinder(h=height, r=1, center=false);
}

module grip_path(width, depth, length, shift) {
    hull() {
        translate([0, 0, 0]) oval_disc(width, depth, 1);
        translate([shift, 0, length-1]) oval_disc(width, depth, 1);
    }
}

module rib_at(z, scale_extra=1.06) {
    x = path_shift * (z / grip_length);
    translate([x, 0, z])
        oval_disc(outer_width * scale_extra, outer_depth * scale_extra, 2.2);
}

module palm_bulge() {
    z = grip_length * 0.72;
    x = path_shift * (z / grip_length) - outer_width * 0.16;
    translate([x, 0, z])
        scale([outer_width * 0.36, outer_depth * 0.62, outer_width * 0.34])
            sphere(r=1);
}

module outer_shape() {
    union() {
        grip_path(outer_width, outer_depth, grip_length, path_shift);

        if (ribbed) {
            for (z = [grip_length*0.18, grip_length*0.33, grip_length*0.48, grip_length*0.63]) {
                rib_at(z);
            }
        }

        if (palm_support) {
            palm_bulge();
        }
    }
}

module inner_channel() {
    // Extend beyond both ends to guarantee a through-channel.
    hull() {
        translate([0, 0, -2]) oval_disc(inner_width, inner_depth, 1);
        translate([path_shift, 0, grip_length+1]) oval_disc(inner_width, inner_depth, 1);
    }
}

difference() {
    outer_shape();
    inner_channel();
}
