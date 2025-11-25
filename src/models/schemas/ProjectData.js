import mongoose from 'mongoose';

// Example schema
const projectDataSchema = new mongoose.Schema({
    // User Reference
    user: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'User',
        required: true,
        index: true
    },

    // Example data fields - replace with project's needs
    title: {
        type: String,
        required: true,
        trim: true,
        maxlength: 200
    },

    description: {
        type: String,
        trim: true,
        maxlength: 1000
    },

    category: {
        type: String,
        enum: ['category1', 'category2', 'category3'], // Define your categories
        required: true
    },

    status: {
        type: String,
        enum: ['draft', 'in-progress', 'completed', 'archived'],
        default: 'draft'
    },

    priority: {
        type: String,
        enum: ['low', 'medium', 'high'],
        default: 'medium'
    },

    // Numeric data
    score: {
        type: Number,
        min: 0,
        max: 100,
        default: 0
    },

    // Tags or labels
    tags: [{
        type: String,
        trim: true,
        lowercase: true
    }],

    // Additional metadata
    metadata: {
        source: String,
        lastModified: { type: Date, default: Date.now },
        version: { type: Number, default: 1 }
    },

    // Completion tracking
    completedAt: {
        type: Date,
        default: null
    }
}, {
    timestamps: true,
    toJSON: { virtuals: true },
    toObject: { virtuals: true }
});

// Indexes
projectDataSchema.index({ user: 1, status: 1 });
projectDataSchema.index({ category: 1, priority: 1 });
projectDataSchema.index({ createdAt: -1 });

// Virtual for completion status
projectDataSchema.virtual('isCompleted').get(function() {
    return this.status === 'completed';
});

// Instance methods
projectDataSchema.methods.markCompleted = function() {
    this.status = 'completed';
    this.completedAt = new Date();
    return this.save();
};

projectDataSchema.methods.updateScore = function(newScore) {
    this.score = Math.max(0, Math.min(100, newScore));
    this.metadata.lastModified = new Date();
    this.metadata.version += 1;
    return this.save();
};

// Static methods
projectDataSchema.statics.findByUser = function(userId) {
    return this.find({ user: userId }).sort({ createdAt: -1 });
};

projectDataSchema.statics.findByCategory = function(category) {
    return this.find({ category }).sort({ createdAt: -1 });
};

projectDataSchema.statics.getCompletedByUser = function(userId) {
    return this.find({ user: userId, status: 'completed' }).sort({ completedAt: -1 });
};

const ProjectData = mongoose.model('ProjectData', projectDataSchema);

export default ProjectData;
